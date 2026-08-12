"""规则管理 API (银行语义, 6 个端点)"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.engine.rule import validate_rule_score_level
from app.models_risk import RiskRule
from app.schemas import RuleCreate, RuleListResponse, RuleResponse, RuleUpdate
from app.service.action_log import record_action

rule_router = APIRouter(prefix="/api/rules", tags=["规则管理"])


def _rule_to_response(r: RiskRule) -> RuleResponse:
    return RuleResponse(
        rule_id=r.rule_id, rule_name=r.rule_name, rule_category=r.rule_category,
        event_type=r.event_type, rule_condition=r.condition_dict,
        risk_level=r.risk_level, risk_score=r.risk_score, action=r.action,
        is_enabled=r.is_enabled, priority=r.priority, description=r.description,
        create_time=r.create_time, update_time=r.update_time)


# 风险等级按语义排序：低=1, 中=2, 高=3, 极高=4
_LEVEL_RANK = case(
    (RiskRule.risk_level == "低", 1),
    (RiskRule.risk_level == "中", 2),
    (RiskRule.risk_level == "高", 3),
    (RiskRule.risk_level == "极高", 4),
)
_SORT_WHITELIST = {
    "rule_id": RiskRule.rule_id,
    "risk_score": RiskRule.risk_score,
    "priority": RiskRule.priority,
    "risk_level": _LEVEL_RANK,
}


@rule_router.get("", response_model=RuleListResponse)
async def api_list_rules(
    category: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query(None),
    order: str = Query("desc"),
    db: AsyncSession = Depends(get_db_async),
):
    filters = [RiskRule.deleted_at.is_(None)]
    if category:
        filters.append(RiskRule.rule_category == category)
    total = int((await db.execute(select(func.count()).select_from(RiskRule).where(*filters))).scalar() or 0)

    # 白名单校验，非法值回退默认 priority.desc()
    sort_col = _SORT_WHITELIST.get(sort_by) if sort_by else None
    if sort_col is None:
        sort_col = RiskRule.priority
        order = "desc"
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    rows = (await db.execute(
        select(RiskRule).where(*filters).order_by(order_expr)
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return RuleListResponse(items=[_rule_to_response(r) for r in rows], total=total, page=page, page_size=page_size)


@rule_router.get("/{rule_id}", response_model=RuleResponse)
async def api_get_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    r = (await db.execute(select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "规则不存在")
    return _rule_to_response(r)


@rule_router.post("", response_model=RuleResponse, status_code=201)
async def api_create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db_async)):
    try:
        validate_rule_score_level(data.risk_level, data.risk_score)
    except Exception as e:
        raise HTTPException(400, str(e))
    if (await db.execute(select(RiskRule).where(RiskRule.rule_id == data.rule_id))).scalar_one_or_none():
        raise HTTPException(409, f"规则ID已存在: {data.rule_id}")
    r = RiskRule(
        rule_id=data.rule_id, rule_name=data.rule_name, rule_category=data.rule_category,
        event_type=data.event_type, rule_condition=__import__("json").dumps(data.rule_condition, ensure_ascii=False),
        risk_level=data.risk_level, risk_score=data.risk_score, action=data.action,
        priority=data.priority, description=data.description)
    db.add(r)
    await db.flush()
    await record_action(db, operator="admin", action_type="CREATE_RULE", target_type="rule",
        target_id=r.rule_id, after_value=data.model_dump(mode="json"),
        remark=f"新增规则 {r.rule_id}")
    await db.commit()
    return _rule_to_response(r)


@rule_router.put("/{rule_id}", response_model=RuleResponse)
async def api_update_rule(rule_id: str, data: RuleUpdate, db: AsyncSession = Depends(get_db_async)):
    r = (await db.execute(select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "规则不存在")
    if data.risk_level is not None and data.risk_score is not None:
        try:
            validate_rule_score_level(data.risk_level, data.risk_score)
        except Exception as e:
            raise HTTPException(400, str(e))
    update = data.model_dump(exclude_unset=True)
    if "rule_condition" in update:
        update["rule_condition"] = __import__("json").dumps(update["rule_condition"], ensure_ascii=False)
    for k, v in update.items():
        setattr(r, k, v)
    await record_action(db, operator="admin", action_type="UPDATE_RULE", target_type="rule",
        target_id=rule_id, after_value=update, remark=f"更新规则 {rule_id}")
    await db.commit()
    return _rule_to_response(r)


@rule_router.put("/{rule_id}/toggle", response_model=RuleResponse)
async def api_toggle_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    r = (await db.execute(select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "规则不存在")
    r.is_enabled = 0 if r.is_enabled else 1
    await record_action(db, operator="admin", action_type="TOGGLE_RULE", target_type="rule",
        target_id=rule_id, after_value={"is_enabled": r.is_enabled}, remark=f"切换规则 {rule_id}")
    await db.commit()
    return _rule_to_response(r)


@rule_router.delete("/{rule_id}")
async def api_delete_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    r = (await db.execute(select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "规则不存在")
    await record_action(db, operator="admin", action_type="DELETE_RULE", target_type="rule",
        target_id=rule_id, before_value={"rule_name": r.rule_name}, remark=f"删除规则 {rule_id}")
    await db.delete(r)
    await db.commit()
    return {"detail": "已删除"}
