"""规则管理 API (CRUD + 启停 + 软删)"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskRule
from app.schemas import RuleCreate, RuleListResponse, RuleResponse, RuleUpdate
from app.service.action_log import orm_to_dict, record_action

rule_router = APIRouter(prefix="/api/rules", tags=["规则管理"])


@rule_router.get("", response_model=RuleListResponse)
async def api_list_rules(
    category: str = Query(None, description="规则分类筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    """分页列出规则 (含软删过滤)."""
    count_stmt = select(func.count()).select_from(RiskRule).where(RiskRule.deleted_at.is_(None))
    if category:
        count_stmt = count_stmt.where(RiskRule.rule_category == category)
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = select(RiskRule).where(RiskRule.deleted_at.is_(None))
    if category:
        stmt = stmt.where(RiskRule.rule_category == category)
    stmt = (
        stmt.order_by(RiskRule.priority.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return RuleListResponse(
        items=[_rule_to_response(r) for r in result.scalars().all()],
        total=total, page=page, page_size=page_size,
    )


@rule_router.get("/{rule_id}", response_model=RuleResponse)
async def api_get_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _rule_to_response(rule)


@rule_router.post("", response_model=RuleResponse, status_code=201)
async def api_create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db_async)):
    existing = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == data.rule_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="规则ID已存在")

    rule = RiskRule(
        rule_id=data.rule_id,
        rule_name=data.rule_name,
        rule_category=data.rule_category,
        event_type=data.event_type,
        rule_condition=json.dumps(data.rule_condition, ensure_ascii=False),
        risk_level=data.risk_level,
        risk_score=data.risk_score,
        action=data.action,
        priority=data.priority,
        description=data.description,
    )
    db.add(rule)
    await record_action(
        db, operator="admin", action_type="CREATE_RULE",
        target_type="rule", target_id=rule.rule_id,
        after_value=orm_to_dict(rule, ["rule_id", "rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"]),
        remark="创建规则",
    )
    await db.commit()
    return _rule_to_response(rule)


@rule_router.put("/{rule_id}", response_model=RuleResponse)
async def api_update_rule(rule_id: str, data: RuleUpdate, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    before_value = orm_to_dict(rule, ["rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"])
    # exclude_none=True: 显式传 null 的字段不更新 (防前端空值把 NOT NULL 列写成 NULL → 1048)
    for key, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        if key == "rule_condition" and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        setattr(rule, key, value)

    await record_action(
        db, operator="admin", action_type="UPDATE_RULE",
        target_type="rule", target_id=rule.rule_id,
        before_value=before_value,
        after_value=orm_to_dict(rule, ["rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"]),
        remark="更新规则",
    )
    await db.commit()
    return _rule_to_response(rule)


@rule_router.put("/{rule_id}/toggle")
async def api_toggle_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    before_value = {"is_enabled": rule.is_enabled}
    rule.is_enabled = 0 if rule.is_enabled else 1
    await record_action(
        db, operator="admin", action_type="TOGGLE_RULE",
        target_type="rule", target_id=rule.rule_id,
        before_value=before_value, after_value={"is_enabled": rule.is_enabled},
        remark=f"规则{'启用' if rule.is_enabled else '禁用'}",
    )
    await db.commit()
    return {"rule_id": rule_id, "is_enabled": rule.is_enabled}


@rule_router.delete("/{rule_id}")
async def api_delete_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    await record_action(
        db, operator="admin", action_type="DELETE_RULE",
        target_type="rule", target_id=rule.rule_id,
        before_value=orm_to_dict(rule, ["rule_id", "rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"]),
        after_value=None,
        remark="删除规则",
    )
    # 软删除 (P3-M9): 设 deleted_at, 不物理删
    rule.deleted_at = __import__("datetime").datetime.now()
    await db.commit()
    return {"detail": "已删除"}


# ORM → Pydantic 响应: 显式列字段避免暴露 _sa_instance_state
def _rule_to_response(rule: RiskRule) -> RuleResponse:
    return RuleResponse(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        rule_category=rule.rule_category,
        event_type=rule.event_type,
        rule_condition=rule.condition_dict,  # @property 自动 JSON 反序列化
        risk_level=rule.risk_level,
        risk_score=rule.risk_score,
        action=rule.action,
        is_enabled=rule.is_enabled,
        priority=rule.priority,
        description=rule.description,
        create_time=rule.create_time,
        update_time=rule.update_time,
    )


# ============================================================
# Demo: 列出 rule router 6 个端点
# 跑法: python -m app.routers.rule
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Router Rule — 6 个端点 (CRUD + 启停)")
    print("=" * 60)
    for route in rule_router.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = "|".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
            print(f"  {methods:<10} {route.path}")

    example = {
        "rule_id": "R031",
        "rule_name": "Demo 规则",
        "rule_category": "综合风险",
        "event_type": "通用",
        "rule_condition": {"field": "order_total_amount", "op": ">=", "value": 100000},
        "risk_level": "高",
        "risk_score": 50,
        "action": "人工审核",
        "priority": 70,
        "description": "单笔≥10万即中等风险",
    }
    print(f"\nPOST /api/rules 创建规则 (示例):\n{json.dumps(example, ensure_ascii=False, indent=2)}")
