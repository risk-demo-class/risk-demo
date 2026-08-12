"""规则管理 API (CRUD + 启停)"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.engine.rule import validate_rule_score_level
from app.models_risk import TelecomRiskRule
from app.schemas import RuleCreate, RuleListResponse, RuleResponse, RuleUpdate

rule_router = APIRouter(prefix="/api/rules", tags=["规则管理"])


def _to_response(r: TelecomRiskRule) -> RuleResponse:
    return RuleResponse(
        rule_id=r.rule_id, rule_name=r.rule_name, rule_category=r.rule_category,
        event_type=r.event_type, rule_condition=r.condition_dict,
        risk_level=r.risk_level, risk_score=r.risk_score, action=r.action,
        is_enabled=r.is_enabled, priority=r.priority, description=r.description,
        create_time=r.create_time,
    )


@rule_router.get("", response_model=RuleListResponse)
async def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db_async),
):
    """分页查询规则 (未软删)."""
    stmt = select(TelecomRiskRule).where(TelecomRiskRule.deleted_at.is_(None))
    if event_type:
        stmt = stmt.where(TelecomRiskRule.event_type.in_([event_type, "通用"]))
    total = int((await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(TelecomRiskRule.priority.desc(), TelecomRiskRule.rule_id)
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return RuleListResponse(
        items=[_to_response(r) for r in rows], total=total, page=page, page_size=page_size,
    )


@rule_router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db_async)):
    """创建规则 (校验 score/level 一致性 + rule_id 唯一)."""
    validate_rule_score_level(data.risk_level, data.risk_score)
    existing = (await db.execute(
        select(TelecomRiskRule.rule_id).where(TelecomRiskRule.rule_id == data.rule_id)
    )).first()
    if existing:
        raise HTTPException(400, f"规则ID已存在: {data.rule_id}")
    rule = TelecomRiskRule(
        rule_id=data.rule_id, rule_name=data.rule_name, rule_category=data.rule_category,
        event_type=data.event_type,
        rule_condition=json.dumps(data.rule_condition, ensure_ascii=False),
        risk_level=data.risk_level, risk_score=data.risk_score, action=data.action,
        is_enabled=1, priority=data.priority, description=data.description,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@rule_router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: str, data: RuleUpdate, db: AsyncSession = Depends(get_db_async)):
    """更新规则 (部分字段)."""
    rule = (await db.execute(
        select(TelecomRiskRule).where(
            TelecomRiskRule.rule_id == rule_id, TelecomRiskRule.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, f"规则不存在: {rule_id}")
    update_data = data.model_dump(exclude_unset=True)
    if "risk_level" in update_data or "risk_score" in update_data:
        validate_rule_score_level(
            update_data.get("risk_level", rule.risk_level),
            update_data.get("risk_score", rule.risk_score),
        )
    if "rule_condition" in update_data:
        rule.rule_condition = json.dumps(update_data.pop("rule_condition"), ensure_ascii=False)
    for k, v in update_data.items():
        setattr(rule, k, v)
    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@rule_router.patch("/{rule_id}/toggle")
async def toggle_rule(rule_id: str, enabled: int = Query(..., ge=0, le=1),
                      db: AsyncSession = Depends(get_db_async)):
    """启停规则 (0=停用, 1=启用)."""
    rule = (await db.execute(
        select(TelecomRiskRule).where(TelecomRiskRule.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, f"规则不存在: {rule_id}")
    rule.is_enabled = enabled
    await db.commit()
    return {"rule_id": rule_id, "is_enabled": enabled}


@rule_router.delete("/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    """软删规则."""
    rule = (await db.execute(
        select(TelecomRiskRule).where(
            TelecomRiskRule.rule_id == rule_id, TelecomRiskRule.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, f"规则不存在: {rule_id}")
    from datetime import datetime
    rule.deleted_at = datetime.now()
    await db.commit()
    return {"rule_id": rule_id, "deleted": True}
