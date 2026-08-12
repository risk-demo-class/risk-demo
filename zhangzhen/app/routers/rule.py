"""银行风控规则管理 API。"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.engine.feature import FEATURE_COLUMNS
from app.engine.rule import normalize_condition
from app.models import RiskLevel, RuleEventType
from app.models_risk import (
    ActionTargetType,
    ActionType,
    RiskRule,
    RuleCategory,
)
from app.schemas import RuleCreate, RuleListResponse, RuleResponse, RuleUpdate
from app.service.action_log import record_action, selected_fields


router = APIRouter(prefix="/api/rules", tags=["规则管理"])
VALID_OPERATORS = {">", ">=", "<", "<=", "==", "!=", "in", "not_in", "between"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _validate_condition(condition: dict[str, Any]) -> None:
    logical_keys = [key for key in ("and", "or") if key in condition]
    if logical_keys:
        if len(logical_keys) != 1 or len(condition) != 1:
            raise HTTPException(status_code=400, detail="AND/OR 分组不能混入单条件字段")
        children = condition[logical_keys[0]]
        if not isinstance(children, list) or not children:
            raise HTTPException(status_code=400, detail="AND/OR 分组至少包含一个条件")
        for child in children:
            if not isinstance(child, dict):
                raise HTTPException(status_code=400, detail="规则子条件必须是 JSON 对象")
            _validate_condition(child)
        return

    field = condition.get("field")
    operator = condition.get("op")
    if field not in FEATURE_COLUMNS:
        raise HTTPException(status_code=400, detail=f"未知的银行特征字段：{field}")
    if operator not in VALID_OPERATORS:
        raise HTTPException(status_code=400, detail=f"不支持的规则运算符：{operator}")
    if "value" not in condition:
        raise HTTPException(status_code=400, detail="单条件必须包含 value")
    if operator == "between":
        value = condition["value"]
        if not isinstance(value, list) or len(value) != 2:
            raise HTTPException(status_code=400, detail="between 的 value 必须是两个值的数组")
    if operator in {"in", "not_in"} and not isinstance(condition["value"], list):
        raise HTTPException(status_code=400, detail=f"{operator} 的 value 必须是数组")


def _validate_score_level(level: RiskLevel, score: int) -> None:
    ranges = {
        RiskLevel.LOW: range(0, 30),
        RiskLevel.MEDIUM: range(30, 60),
        RiskLevel.HIGH: range(60, 85),
        RiskLevel.EXTREME: range(85, 101),
    }
    if score not in ranges[level]:
        raise HTTPException(
            status_code=400,
            detail="风险等级与分值不匹配：低0-29、中30-59、高60-84、极高85-100",
        )


def _response(rule: RiskRule) -> RuleResponse:
    condition = normalize_condition(rule.rule_condition)
    return RuleResponse(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        rule_category=rule.rule_category,
        event_type=rule.event_type,
        rule_condition=condition or {},
        risk_level=rule.risk_level,
        risk_score=rule.risk_score,
        action=rule.action,
        is_enabled=rule.is_enabled,
        priority=rule.priority,
        description=rule.description,
        create_time=rule.create_time,
        update_time=rule.update_time,
    )


@router.get("", response_model=RuleListResponse)
async def list_rules(
    category: RuleCategory | None = None,
    event_type: RuleEventType | None = None,
    enabled: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
) -> RuleListResponse:
    filters: list[Any] = [RiskRule.deleted_at.is_(None)]
    if category is not None:
        filters.append(RiskRule.rule_category == category)
    if event_type is not None:
        filters.append(RiskRule.event_type == event_type)
    if enabled is not None:
        filters.append(RiskRule.is_enabled.is_(enabled))
    total = int(
        (await db.execute(select(func.count(RiskRule.rule_id)).where(*filters))).scalar_one()
        or 0
    )
    rows = (
        await db.execute(
            select(RiskRule)
            .where(*filters)
            .order_by(RiskRule.priority.desc(), RiskRule.rule_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return RuleListResponse(
        items=[_response(rule) for rule in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)) -> RuleResponse:
    rule = await db.get(RiskRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _response(rule)


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    data: RuleCreate,
    db: AsyncSession = Depends(get_db_async),
) -> RuleResponse:
    _validate_condition(data.rule_condition)
    _validate_score_level(data.risk_level, data.risk_score)
    now = _now()
    async with db.begin():
        existing = await db.get(RiskRule, data.rule_id)
        if existing is not None:
            raise HTTPException(status_code=409, detail="规则ID已存在")
        rule = RiskRule(**data.model_dump(), create_time=now, update_time=now)
        db.add(rule)
        await record_action(
            db,
            operator="admin",
            action_type=ActionType.CREATE_RULE,
            target_type=ActionTargetType.RULE,
            target_id=rule.rule_id,
            after_value=data.model_dump(mode="json"),
            remark="创建银行风控规则",
        )
        await db.flush()
    return _response(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str,
    data: RuleUpdate,
    db: AsyncSession = Depends(get_db_async),
) -> RuleResponse:
    async with db.begin():
        rule = await db.get(RiskRule, rule_id)
        if rule is None or rule.deleted_at is not None:
            raise HTTPException(status_code=404, detail="规则不存在")
        changes = data.model_dump(exclude_unset=True)
        condition = changes.get("rule_condition")
        if condition is not None:
            _validate_condition(condition)
        new_level = changes.get("risk_level", rule.risk_level)
        new_score = changes.get("risk_score", rule.risk_score)
        _validate_score_level(new_level, new_score)
        before = selected_fields(
            rule,
            "rule_name",
            "rule_category",
            "event_type",
            "rule_condition",
            "risk_level",
            "risk_score",
            "action",
            "is_enabled",
            "priority",
            "description",
        )
        for name, value in changes.items():
            setattr(rule, name, value)
        rule.update_time = _now()
        await record_action(
            db,
            operator="admin",
            action_type=ActionType.UPDATE_RULE,
            target_type=ActionTargetType.RULE,
            target_id=rule.rule_id,
            before_value=before,
            after_value=selected_fields(rule, *before.keys()),
            remark="更新银行风控规则",
        )
        await db.flush()
    return _response(rule)


@router.put("/{rule_id}/toggle")
async def toggle_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)) -> dict[str, Any]:
    async with db.begin():
        rule = await db.get(RiskRule, rule_id)
        if rule is None or rule.deleted_at is not None:
            raise HTTPException(status_code=404, detail="规则不存在")
        before = rule.is_enabled
        rule.is_enabled = not rule.is_enabled
        rule.update_time = _now()
        await record_action(
            db,
            operator="admin",
            action_type=ActionType.TOGGLE_RULE,
            target_type=ActionTargetType.RULE,
            target_id=rule.rule_id,
            before_value={"is_enabled": before},
            after_value={"is_enabled": rule.is_enabled},
            remark="启停银行风控规则",
        )
    return {"rule_id": rule.rule_id, "is_enabled": rule.is_enabled}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)) -> dict[str, str]:
    async with db.begin():
        rule = await db.get(RiskRule, rule_id)
        if rule is None or rule.deleted_at is not None:
            raise HTTPException(status_code=404, detail="规则不存在")
        rule.deleted_at = _now()
        rule.is_enabled = False
        rule.update_time = rule.deleted_at
        await record_action(
            db,
            operator="admin",
            action_type=ActionType.DELETE_RULE,
            target_type=ActionTargetType.RULE,
            target_id=rule.rule_id,
            before_value={"deleted_at": None, "is_enabled": True},
            after_value={"deleted_at": rule.deleted_at, "is_enabled": False},
            remark="软删除银行风控规则",
        )
    return {"detail": "规则已软删除"}
