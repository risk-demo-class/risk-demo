"""规则管理接口"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.rule import evaluate_condition
from app.models import RiskRule

router = APIRouter(prefix="/api/rules", tags=["规则管理"])


@router.get("")
async def list_rules(event_type: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(RiskRule).where(RiskRule.is_deleted.is_(False),
                                  RiskRule.deleted_at.is_(None)).order_by(RiskRule.priority.desc())
    if event_type:
        stmt = stmt.where(RiskRule.event_type == event_type)
    rules = (await db.execute(stmt)).scalars().all()
    return [{
        "rule_id": r.rule_id, "rule_name": r.rule_name, "rule_category": r.rule_category,
        "event_type": r.event_type, "rule_condition": r.rule_condition,
        "risk_level": r.risk_level, "risk_score": r.risk_score, "action": r.action,
        "is_enabled": r.is_enabled, "priority": r.priority, "description": r.description,
    } for r in rules]


@router.post("")
async def create_rule(payload: dict, db: AsyncSession = Depends(get_db)):
    """新建规则(教学: 模拟 INSERT INTO risk_rule)。"""
    rule = RiskRule(
        rule_id=payload["rule_id"],
        rule_name=payload["rule_name"],
        rule_category=payload.get("rule_category", "通用"),
        event_type=payload.get("event_type", "通用"),
        rule_condition=payload["rule_condition"],
        risk_level=payload.get("risk_level", "中"),
        risk_score=payload.get("risk_score", 40),
        action=payload.get("action", "标记"),
        is_enabled=payload.get("is_enabled", True),
        priority=payload.get("priority", 50),
        description=payload.get("description", ""),
    )
    db.add(rule)
    await db.commit()
    return {"rule_id": rule.rule_id, "message": "创建成功"}


@router.post("/test")
async def test_rule(payload: dict, db: AsyncSession = Depends(get_db)):
    """测试一条规则对一组特征是否命中。"""
    return {"hit": evaluate_condition(payload["rule_condition"], payload["features"])}


@router.patch("/{rule_id}/toggle")
async def toggle_rule(rule_id: str, is_enabled: bool, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(RiskRule).where(RiskRule.rule_id == rule_id))
    rule = r.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, f"规则不存在: {rule_id}")
    rule.is_enabled = is_enabled
    await db.commit()
    return {"rule_id": rule_id, "is_enabled": is_enabled}
