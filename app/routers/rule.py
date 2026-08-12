"""规则管理 API"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_risk import RiskRule
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
    """分页列出规则 (P4-L4 2026-08-08: 对齐 assessments/cases 的 {items, total} 模式)."""
    # 软删: 所有 SELECT 过滤 deleted_at IS NULL
    alive = RiskRule.deleted_at.is_(None)

    # 1 次 COUNT
    count_stmt = select(func.count()).select_from(RiskRule).where(alive)
    if category:
        count_stmt = count_stmt.where(RiskRule.rule_category == category)
    total = int((await db.execute(count_stmt)).scalar() or 0)

    # 1 次 paged SELECT: 恢复为 "按权重 priority DESC (第 1 键, 同权重按修改时间, 再 id)"
    #   排序 3 级:
    #     1) priority DESC                         ← 第 1 键: 权重/优先级 (高优先级规则在最顶)
    #     2) coalesce(update_time, create_time) DESC ← 同权重下: 最新修改/新建排第 1
    #        ⭐ coalesce 兜底老数据: INSERT 时 update_time 可能为 NULL/零值, 退化用 create_time.
    #        ⭐ 同时 CREATE 时显式写 create_time=update_time=now (见 api_create_rule),
    #          避免 priority=0 组里新建的规则因为 update_time=NULL 被排到整库最后.
    #     3) rule_id DESC                          ← 时间也相同的两条, id 大的在前 (兜底稳定)
    time_sort = func.coalesce(RiskRule.update_time, RiskRule.create_time).desc()

    stmt = select(RiskRule).where(alive)
    if category:
        stmt = stmt.where(RiskRule.rule_category == category)
    stmt = (
        stmt.order_by(
            RiskRule.priority.desc(),   # 第 1 键: 权重 / 优先级 (恢复之前的权重排序)
            time_sort,                   # 第 2 键: 同权重按修改时间
            RiskRule.rule_id.desc(),     # 第 3 键: id 倒序
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return RuleListResponse(
        items=[_rule_to_response(r) for r in result.scalars().all()],
        total=total, page=page, page_size=page_size,
    )


# 软删过滤公共条件 (避免 L001 规则 "没了" 的 Bug)
_alive = RiskRule.deleted_at.is_(None)


@rule_router.get("/{rule_id}", response_model=RuleResponse)
async def api_get_rule(rule_id: str, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id, _alive)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _rule_to_response(rule)


@rule_router.post("", response_model=RuleResponse, status_code=201)
async def api_create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db_async)):
    existing = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == data.rule_id, _alive)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="规则ID已存在")

    now = datetime.now()
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
        # ⭐ CREATE 时显式写 create_time + update_time.
        # RiskRule.update_time 虽然有 Column(..., onupdate=datetime.now),
        # 但 onupdate 只在 ORM UPDATE 时才触发; INSERT 时如果列只设了
        # default=CURRENT_TIMESTAMP (DB 端), Python 端读不到, commit 后
        # ORDER BY update_time DESC 会把 NULL 排到最末尾 → 新规则跑到最后.
        create_time=now,
        update_time=now,
    )
    db.add(rule)
    await record_action(
        db, operator="admin", action_type="CREATE_RULE",
        target_type="rule", target_id=rule.rule_id,
        after_value=orm_to_dict(rule, ["rule_id", "rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"]),
        remark="创建规则 (显式填 create_time=update_time=now, 保证排序键生效)",
    )
    await db.commit()
    return _rule_to_response(rule)


@rule_router.put("/{rule_id}", response_model=RuleResponse)
async def api_update_rule(rule_id: str, data: RuleUpdate, db: AsyncSession = Depends(get_db_async)):
    rule = (await db.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id, _alive)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # exclude_unset=True: 只取调用方显式传的字段, 避免空更新覆盖已有数据
    before_value = orm_to_dict(rule, ["rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"])
    for key, value in data.model_dump(exclude_unset=True).items():
        # rule_condition 是嵌套 dict, 需要重新 JSON 序列化
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
        select(RiskRule).where(RiskRule.rule_id == rule_id, _alive)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # is_enabled 是 INT (0/1) 不是 BOOL, MySQL BOOL 实际是 TINYINT
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
        select(RiskRule).where(RiskRule.rule_id == rule_id, _alive)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    await record_action(
        db, operator="admin", action_type="DELETE_RULE",
        target_type="rule", target_id=rule.rule_id,
        before_value=orm_to_dict(rule, ["rule_id", "rule_name", "risk_level", "risk_score", "action", "is_enabled", "priority"]),
        after_value=None,
        remark="删除规则 (软删: deleted_at = now())",
    )
    # 软删: 直接 UPDATE deleted_at (保留数据, 列表/查询自动过滤掉)
    rule.deleted_at = datetime.now()
    # 显式改 update_time (onupdate 可能对 deleted_at 的改动不触发)
    rule.update_time = rule.deleted_at
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
# Demo: 列出 rule router 6 个端点 (完整 CRUD + toggle)
# 跑法: python app/routers/rule.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Router Rule — 6 个端点 (CRUD + 启停)")
    print("=" * 60)

    # 1. 列出 6 端点
    print("\n[1] 注册的 6 个端点 (CRUD + 启停):")
    for route in rule_router.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = "|".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
            status = f" (status={route.status_code})" if hasattr(route, "status_code") and route.status_code else ""
            print(f"  {methods:<10} {route.path}{status}")

    # 2. endpoint 业务说明
    print("\n[2] 各端点用途:")
    descriptions = [
        ("GET    /api/rules",          "列出所有规则 (含禁用的)"),
        ("GET    /api/rules/{id}",     "查单条规则详情"),
        ("POST   /api/rules",          "创建规则 (status=201)"),
        ("PUT    /api/rules/{id}",     "更新规则 (全字段可改)"),
        ("PUT    /api/rules/{id}/toggle", "切换启停 (1 ↔ 0)"),
        ("DELETE /api/rules/{id}",     "软删除 (P3-M9: 设 deleted_at)"),
    ]
    for method_path, desc in descriptions:
        print(f"  {method_path:<35}  {desc}")

    # 3. 创建规则示例
    print("\n[3] POST /api/rules 创建规则 (示例):")
    example = {
        "rule_id": "R031",
        "rule_name": "Demo 规则",
        "rule_category": "订单欺诈",
        "event_type": "下单",
        "rule_condition": {"field": "order_total_amount", "op": ">=", "value": 1000},
        "risk_level": "高",
        "risk_score": 50,
        "action": "人工审核",
        "priority": 70,
        "description": "单笔≥1000 即中等风险",
    }
    import json
    print(json.dumps(example, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("总结: 6 端点覆盖规则全生命周期 (CRUD + 启停 + 软删), audit 自动记 P4-L1")
