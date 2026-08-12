"""规则管理 API: 增删改查 + 启停 + 审计"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.engine.rule import RuleScoreLevelMismatchError, validate_rule_score_level
from app.models import RiskRule
from app.schemas import RuleCreate, RuleListResponse, RuleResponse, RuleUpdate
from app.service.action_log import record_action

logger = logging.getLogger(__name__)

rule_router = APIRouter(prefix="/api/rules", tags=["规则管理"])


def _to_response(rule: RiskRule) -> RuleResponse:
    return RuleResponse(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        rule_category=rule.rule_category,
        event_type=rule.event_type,
        rule_condition=rule.condition_dict,
        risk_level=rule.risk_level,
        risk_score=rule.risk_score,
        action=rule.action,
        is_enabled=rule.is_enabled,
        priority=rule.priority,
        description=rule.description,
        create_time=rule.create_time,
        update_time=rule.update_time,
    )


@rule_router.get("", response_model=RuleListResponse)
async def list_rules(
    page: int = 1,
    page_size: int = 10,
    keyword: str = "",
    category: str = "",
    event_type: str = "",
    db: AsyncSession = Depends(get_db_async),
):
    stmt = select(RiskRule).where(RiskRule.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(RiskRule).where(RiskRule.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(RiskRule.rule_id.like(like) | RiskRule.rule_name.like(like))
        count_stmt = count_stmt.where(RiskRule.rule_id.like(like) | RiskRule.rule_name.like(like))
    if category:
        stmt = stmt.where(RiskRule.rule_category == category)
        count_stmt = count_stmt.where(RiskRule.rule_category == category)
    if event_type:
        stmt = stmt.where(RiskRule.event_type == event_type)
        count_stmt = count_stmt.where(RiskRule.event_type == event_type)

    total = int((await db.execute(count_stmt)).scalar() or 0)
    stmt = stmt.order_by(RiskRule.priority.desc()).offset((page - 1) * page_size).limit(page_size)
    rules = (await db.execute(stmt)).scalars().all()
    return RuleListResponse(
        items=[_to_response(r) for r in rules],
        total=total,
        page=page,
        page_size=page_size,
    )


@rule_router.post("", response_model=RuleResponse)
async def create_rule(body: RuleCreate, db: AsyncSession = Depends(get_db_async)):
    existing = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == body.rule_id)
    )).scalar_one_or_none()
    if existing:
        if existing.deleted_at is not None:
            # 软删过的规则: 恢复复用 (清空 deleted_at + 更新内容)
            existing.deleted_at = None
            existing.rule_name = body.rule_name
            existing.rule_category = body.rule_category
            existing.event_type = body.event_type
            existing.rule_condition = json.dumps(body.rule_condition, ensure_ascii=False)
            existing.risk_level = body.risk_level
            existing.risk_score = body.risk_score
            existing.action = body.action
            existing.priority = body.priority
            existing.description = body.description
            existing.is_enabled = 1
            await record_action(
                db, "admin", "CREATE_RULE", "rule", body.rule_id,
                after_value=_to_response(existing).model_dump(mode="json"),
                remark=f"恢复软删规则 {body.rule_id}",
            )
            await db.commit()
            await db.refresh(existing)
            return _to_response(existing)
        raise HTTPException(status_code=409, detail=f"规则ID已存在: {body.rule_id}")
    try:
        validate_rule_score_level(body.risk_level, body.risk_score)
    except RuleScoreLevelMismatchError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rule = RiskRule(
        rule_id=body.rule_id,
        rule_name=body.rule_name,
        rule_category=body.rule_category,
        event_type=body.event_type,
        rule_condition=json.dumps(body.rule_condition, ensure_ascii=False),
        risk_level=body.risk_level,
        risk_score=body.risk_score,
        action=body.action,
        priority=body.priority,
        description=body.description,
    )
    db.add(rule)
    await db.flush()  # 触发 Python 侧默认值 (is_enabled=1) + 拿到主键
    await record_action(
        db, "admin", "CREATE_RULE", "rule", body.rule_id,
        after_value=_to_response(rule).model_dump(mode="json"),
        remark=f"创建规则 {body.rule_id}",
    )
    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@rule_router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    return _to_response(rule)


@rule_router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: str, body: RuleUpdate, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")

    before = _to_response(rule).model_dump(mode="json")
    data = body.model_dump(exclude_unset=True)
    if "risk_level" in data or "risk_score" in data:
        try:
            validate_rule_score_level(
                data.get("risk_level", rule.risk_level),
                data.get("risk_score", rule.risk_score),
            )
        except RuleScoreLevelMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if "rule_condition" in data:
        data["rule_condition"] = json.dumps(data["rule_condition"], ensure_ascii=False)
    for k, v in data.items():
        setattr(rule, k, v)

    await record_action(
        db, "admin", "UPDATE_RULE", "rule", rule_id,
        before_value=before,
        after_value=_to_response(rule).model_dump(mode="json"),
        remark=f"更新规则 {rule_id}",
    )
    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@rule_router.delete("/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    """软删除规则 (deleted_at 置位, 保留审计)."""
    from datetime import datetime
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    before = _to_response(rule).model_dump(mode="json")
    rule.deleted_at = datetime.now()
    rule.is_enabled = 0
    await record_action(
        db, "admin", "DELETE_RULE", "rule", rule_id,
        before_value=before,
        after_value=None,
        remark=f"软删除规则 {rule_id}",
    )
    await db.commit()
    return {"success": True, "message": f"规则 {rule_id} 已删除"}


@rule_router.patch("/{rule_id}/toggle")
async def toggle_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    before = _to_response(rule).model_dump(mode="json")
    rule.is_enabled = 0 if rule.is_enabled else 1
    await record_action(
        db, "admin", "TOGGLE_RULE", "rule", rule_id,
        before_value=before,
        after_value={"is_enabled": rule.is_enabled},
        remark=f"{'启用' if rule.is_enabled else '停用'}规则 {rule_id}",
    )
    await db.commit()
    return {"success": True, "rule_id": rule_id, "is_enabled": rule.is_enabled}
