"""
AI Agent 工具集 (8 个制造业工具).

  风控决策工具 (4): 风险检查 / 案件查询 / 经销商画像 / 黑名单管理
  数据分析工具 (4): 仪表盘统计 / 趋势分析 / 规则命中率 / 业务数据查询

架构: 业务实现是 _impl 函数 (纯 async, 零第三方依赖), TOOL_REGISTRY 提供
统一元数据 (name/description/keywords/handler), 两种使用方式:
  1. 内置规则模式: chat.py 按 keywords 关键词匹配意图 → 调 handler
  2. LLM 模式:     llm_agent.py 把 handler 包装成 langchain @tool → DeepAgent
"""
import json
import logging
import ulid
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import (
    CrossRegionReport,
    DealerInfo,
    OrderInfo,
    Product,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskRule,
    WarrantyRecord,
)
from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service.case import (
    add_blacklist,
    check_blacklist,
    count_blacklists_tx,
    get_profile_tx,
    list_blacklists_tx,
)
from app.service.event import process_event

logger = logging.getLogger(__name__)


# ============================================================
# 公共 helper
# ============================================================

async def _safe_call(error_label: str, impl, **kwargs) -> str:
    """8 个工具共享的执行模板: 开 session → 调 impl → 异常转字符串."""
    try:
        async with AsyncSessionLocal() as db:
            return await impl(db=db, **kwargs)
    except Exception as e:
        error_id = f"err_{ulid.new().str.lower()[:12]}"
        logger.exception("%s 执行失败 [error_id=%s] args=%s",
                         error_label, error_id, {k: v for k, v in kwargs.items() if k != "db"})
        return f"{error_label}失败: {e} (error_id={error_id})"


def _row_to_dict(row) -> dict:
    """SQLAlchemy Row → dict (datetime → ISO 字符串, Decimal → float)."""
    item = {}
    for key, val in row._mapping.items():
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "__float__"):
            val = float(val)
        item[key] = val
    return item


# ============================================================
# 1. 风险检查
# ============================================================

async def _risk_check_impl(
    *, db: AsyncSession, user_id: str, event_type: str, source_id: str,
) -> str:
    """对经销商/举报人和事件执行实时风控检查 (走 process_event 4 步 + 7 步流水线)."""
    request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id)
    result = await process_event(db, request)
    return json.dumps({
        "assessment_id": result.assessment_id,
        "user_id": result.user_id,
        "final_score": result.final_score,
        "risk_level": result.risk_level,
        "decision": result.decision,
        "rule_count": result.rule_count,
        "blocked_by": result.blocked_by,
        "triggered_rules": [r.model_dump() for r in result.triggered_rules],
    }, ensure_ascii=False, indent=2)


# ============================================================
# 2. 案件查询
# ============================================================

async def _query_cases_impl(*, db: AsyncSession, status: str, page: int) -> str:
    """查询风控案件列表 + 统计 (组合返回, 1 次调用拿全)."""
    from app.service.case import count_cases_tx, list_cases_tx
    cases = await list_cases_tx(db, status=status or None, page=page, page_size=10)
    total = await count_cases_tx(db, status=status or None)
    stats = await _case_statistics(db)
    return json.dumps({
        "cases": [
            {"case_id": c.case_id, "user_id": c.user_id, "case_status": c.case_status,
             "case_category": c.case_category, "source_id": c.source_id,
             "event_type": c.event_type, "create_time": c.create_time.isoformat() if c.create_time else None}
            for c in cases
        ],
        "total": total,
        "page": page,
        "statistics": stats,
    }, ensure_ascii=False, indent=2)


async def _case_statistics(db: AsyncSession) -> dict:
    rows = (await db.execute(
        select(RiskCase.case_status, func.count()).group_by(RiskCase.case_status)
    )).all()
    stats = {"total": 0, "pending": 0, "reviewing": 0, "approved": 0, "rejected": 0, "closed": 0}
    for status, cnt in rows:
        cnt = int(cnt)
        stats["total"] += cnt
        if status == "待审核":
            stats["pending"] = cnt
        elif status == "审核中":
            stats["reviewing"] = cnt
        elif status == "已通过":
            stats["approved"] = cnt
        elif status == "已拒绝":
            stats["rejected"] = cnt
        elif status == "已关闭":
            stats["closed"] = cnt
    return stats


# ============================================================
# 3. 经销商画像
# ============================================================

async def _query_dealer_profile_impl(*, db: AsyncSession, user_id: str) -> str:
    """查询经销商风险画像. 没评估过时给出提示 + 基础档案信息."""
    try:
        profile = await get_profile_tx(db, user_id)
        return json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)
    except Exception:
        # 没有画像: 返回经销商档案基础信息
        dealer = (await db.execute(
            select(DealerInfo).where(DealerInfo.dealer_id == user_id)
        )).scalar_one_or_none()
        if dealer:
            return json.dumps({
                "user_id": user_id,
                "has_profile": False,
                "dealer_name": dealer.dealer_name,
                "region": dealer.region,
                "contract_start": dealer.contract_start.isoformat() if dealer.contract_start else None,
                "contract_end": dealer.contract_end.isoformat() if dealer.contract_end else None,
                "hint": "该经销商还没做过风控评估, 可先执行一次风险检查",
            }, ensure_ascii=False, indent=2)
        return json.dumps({"user_id": user_id, "has_profile": False,
                           "hint": "经销商档案不存在"}, ensure_ascii=False, indent=2)


# ============================================================
# 4. 黑名单管理 (4 action)
# ============================================================

async def _blacklist_add_impl(
    *, db: AsyncSession, blacklist_type: str, value: str, reason: str,
) -> str:
    result = await add_blacklist(db, BlacklistCreate(
        blacklist_type=blacklist_type, blacklist_value=value, reason=reason,
    ))
    return f"已添加到风控黑名单: {result.model_dump(mode='json')}"


async def _blacklist_check_impl(
    *, db: AsyncSession, blacklist_type: str, value: str, reason: str = "",
) -> str:
    is_blocked = await check_blacklist(db, blacklist_type, value)
    return f"{'在' if is_blocked else '不在'}风控黑名单中: {blacklist_type}={value}"


async def _blacklist_list_impl(*, db: AsyncSession) -> str:
    rows = await list_blacklists_tx(db, page=1, page_size=50)
    total = await count_blacklists_tx(db)
    return json.dumps({
        "total": total,
        "items": [{"blacklist_id": b.blacklist_id, "blacklist_type": b.blacklist_type,
                   "blacklist_value": b.blacklist_value, "reason": b.reason,
                   "expire_time": b.expire_time.isoformat() if b.expire_time else None}
                  for b in rows],
    }, ensure_ascii=False, indent=2)


async def _blacklist_remove_impl(
    *, db: AsyncSession, blacklist_type: str, value: str, reason: str = "",
) -> str:
    bl = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == blacklist_type,
            RiskBlacklist.blacklist_value == value,
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if bl:
        bl.deleted_at = datetime.now()
        await db.commit()
        return f"已从风控黑名单移除: {blacklist_type}={value}"
    return f"未找到黑名单记录: {blacklist_type}={value}"


_BLACKLIST_ACTIONS = {
    "add": _blacklist_add_impl,
    "check": _blacklist_check_impl,
    "list": _blacklist_list_impl,
    "remove": _blacklist_remove_impl,
}


async def _manage_blacklist_impl(
    *, db: AsyncSession, action: str, blacklist_type: str, value: str, reason: str,
) -> str:
    """黑名单管理统一入口 (字典派发 4 个 action)."""
    impl = _BLACKLIST_ACTIONS.get(action)
    if not impl:
        return f"不支持的操作: {action}, 请使用 add/remove/check/list"
    if action == "list":
        # list 不需要 blacklist_type/value/reason, 单独调
        return await impl(db=db)
    return await impl(db=db, blacklist_type=blacklist_type, value=value, reason=reason)


# ============================================================
# 5. 仪表盘统计
# ============================================================

async def _query_dashboard_stats_impl(*, db: AsyncSession) -> str:
    """仪表盘统计: 今日评估 / 待审案件 / 拒绝案件 / 规则数 + 决策分布 + 最近评估."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    assessments_today = int((await db.execute(
        select(func.count()).select_from(RiskAssessment).where(RiskAssessment.create_time >= today_start)
    )).scalar() or 0)
    pending = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    )).scalar() or 0)
    rejected = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "已拒绝")
    )).scalar() or 0)
    rules = int((await db.execute(
        select(func.count()).select_from(RiskRule).where(
            RiskRule.is_enabled == 1, RiskRule.deleted_at.is_(None),
        )
    )).scalar() or 0)
    decision_rows = (await db.execute(
        select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)
    )).all()
    return json.dumps({
        "today_assessments": assessments_today,
        "pending_cases": pending,
        "rejected_cases": rejected,
        "enabled_rules": rules,
        "decision_distribution": {d: int(c) for d, c in decision_rows},
    }, ensure_ascii=False, indent=2)


# ============================================================
# 6. 趋势分析
# ============================================================

async def _analyze_risk_trend_impl(*, db: AsyncSession, days: int) -> str:
    """指定天数内每日评估量 + 风险等级分布 + 决策分布."""
    since = datetime.now() - timedelta(days=days)
    daily = (await db.execute(
        select(
            func.date(RiskAssessment.create_time).label("dt"),
            func.count().label("cnt"),
        ).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since)
        .group_by(func.date(RiskAssessment.create_time))
        .order_by(func.date(RiskAssessment.create_time))
    )).all()
    level_dist = dict((await db.execute(
        select(RiskAssessment.risk_level, func.count().label("cnt"))
        .select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since)
        .group_by(RiskAssessment.risk_level)
    )).all())
    decision_dist = dict((await db.execute(
        select(RiskAssessment.decision, func.count().label("cnt"))
        .select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since)
        .group_by(RiskAssessment.decision)
    )).all())
    return json.dumps({
        "period_days": days,
        "daily_counts": [{"date": str(r.dt), "count": int(r.cnt)} for r in daily],
        "risk_level_distribution": {k: int(v) for k, v in level_dist.items()},
        "decision_distribution": {k: int(v) for k, v in decision_dist.items()},
    }, ensure_ascii=False, indent=2)


# ============================================================
# 7. 规则命中率分析
# ============================================================

async def _analyze_rule_effectiveness_impl(*, db: AsyncSession) -> str:
    """所有启用规则的命中率 (用最近 500 条评估样本近似)."""
    total = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
    )).scalar() or 0)
    rules = (await db.execute(
        select(RiskRule).where(RiskRule.is_enabled == 1).order_by(RiskRule.priority.desc())
    )).scalars().all()

    # 统计最近 500 条评估里每条规则命中次数
    rows = (await db.execute(
        select(RiskAssessment.rule_results)
        .order_by(RiskAssessment.create_time.desc())
        .limit(500)
    )).all()
    counter: dict[str, int] = {}
    for r in rows:
        if not r.rule_results:
            continue
        try:
            for hit in json.loads(r.rule_results):
                rid = hit.get("rule_id")
                if rid:
                    counter[rid] = counter.get(rid, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    return json.dumps({
        "total_assessments": total,
        "rules": [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "category": r.rule_category,
                "score": r.risk_score,
                "hit_count": counter.get(r.rule_id, 0),
                "hit_rate_pct": round(counter.get(r.rule_id, 0) / total * 100, 2) if total > 0 else 0,
            }
            for r in rules
        ],
    }, ensure_ascii=False, indent=2)


# ============================================================
# 8. 业务数据查询 (6 query_type)
# ============================================================

async def _biz_dealer_orders(db: AsyncSession, dealer_id: str, order_id: str, limit: int) -> list:
    """经销商的订货单."""
    stmt = (
        select(OrderInfo.order_id, OrderInfo.product_id, OrderInfo.quantity,
               OrderInfo.unit_price, OrderInfo.total_amount,
               OrderInfo.ship_to_region, OrderInfo.create_time)
        .where(OrderInfo.dealer_id == dealer_id)
        .order_by(OrderInfo.create_time.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).all())


async def _biz_dealer_info(db: AsyncSession, dealer_id: str, order_id: str, limit: int) -> list:
    """经销商档案."""
    stmt = select(DealerInfo).where(DealerInfo.dealer_id == dealer_id).limit(1)
    return list((await db.execute(stmt)).all())


async def _biz_warranty_list(db: AsyncSession, dealer_id: str, order_id: str, limit: int) -> list:
    """经销商的保修/维修记录 (JOIN 订单)."""
    stmt = (
        select(WarrantyRecord.warranty_id, WarrantyRecord.product_sn,
               WarrantyRecord.order_id, WarrantyRecord.issue_date,
               WarrantyRecord.issue_type, WarrantyRecord.repair_cost,
               WarrantyRecord.technician_id)
        .join(OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id)
        .where(OrderInfo.dealer_id == dealer_id)
        .order_by(WarrantyRecord.issue_date.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).all())


async def _biz_report_list(db: AsyncSession, dealer_id: str, order_id: str, limit: int) -> list:
    """串货举报记录 (按被举报经销商或订单)."""
    stmt = select(
        CrossRegionReport.report_id, CrossRegionReport.order_id,
        CrossRegionReport.dealer_id, CrossRegionReport.ship_to_region,
        CrossRegionReport.dealer_region, CrossRegionReport.reporter_id,
        CrossRegionReport.create_time,
    )
    if dealer_id:
        stmt = stmt.where(CrossRegionReport.dealer_id == dealer_id)
    if order_id:
        stmt = stmt.where(CrossRegionReport.order_id == order_id)
    stmt = stmt.order_by(CrossRegionReport.create_time.desc()).limit(limit)
    return list((await db.execute(stmt)).all())


async def _biz_order_detail(db: AsyncSession, dealer_id: str, order_id: str, limit: int) -> list:
    """订单详情 (JOIN 产品拿名称/MSRP)."""
    stmt = (
        select(OrderInfo.order_id, OrderInfo.dealer_id, OrderInfo.product_id,
               Product.name.label("product_name"), Product.msrp,
               OrderInfo.quantity, OrderInfo.unit_price, OrderInfo.total_amount,
               OrderInfo.ship_to_region, OrderInfo.create_time)
        .join(Product, OrderInfo.product_id == Product.product_id)
        .where(OrderInfo.order_id == order_id)
        .limit(limit)
    )
    return list((await db.execute(stmt)).all())


async def _biz_recent_orders(db: AsyncSession, dealer_id: str, order_id: str, limit: int) -> list:
    """系统最近的订货单 (管理员视角)."""
    stmt = (
        select(OrderInfo.order_id, OrderInfo.dealer_id, OrderInfo.product_id,
               OrderInfo.quantity, OrderInfo.total_amount,
               OrderInfo.ship_to_region, OrderInfo.create_time)
        .order_by(OrderInfo.create_time.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).all())


_BIZ_QUERY_HANDLERS = {
    "dealer_orders": _biz_dealer_orders,
    "dealer_info": _biz_dealer_info,
    "warranty_list": _biz_warranty_list,
    "report_list": _biz_report_list,
    "order_detail": _biz_order_detail,
    "recent_orders": _biz_recent_orders,
}


async def _query_business_data_impl(
    *, db: AsyncSession, query_type: str, dealer_id: str, order_id: str, limit: int,
) -> str:
    """业务数据查询统一入口 (字典派发 6 种 query_type)."""
    handler = _BIZ_QUERY_HANDLERS.get(query_type)
    if not handler:
        return f"不支持的查询类型: {query_type}, 可选: {', '.join(_BIZ_QUERY_HANDLERS)}"
    rows = await handler(db, dealer_id, order_id, limit)
    return json.dumps(
        [_row_to_dict(r) for r in rows],
        ensure_ascii=False, indent=2,
    )


# ============================================================
# 工具注册表 (内置规则模式 + LLM 模式共用)
# ============================================================

TOOL_REGISTRY = [
    {
        "name": "risk_check",
        "description": "对指定经销商/用户和事件执行实时风险检查。参数: user_id(经销商ID,如 D002)、event_type(经销商订货/保修申请/售后维修/串货举报)、source_id(订单/保修单/举报单ID)。返回评分、等级、决策、命中规则。",
        "keywords": ["风险检查", "风控检查", "评估一下", "查风险", "执行检查", "风险如何", "check"],
        "handler": _risk_check_impl,
        "arg_names": ["user_id", "event_type", "source_id"],
    },
    {
        "name": "query_cases",
        "description": "查询风控案件列表。参数: status(待审核/审核中/已通过/已拒绝/已关闭, 空=全部)、page(页码)。返回案件列表 + 统计。",
        "keywords": ["案件", "待审核", "待办", "审核", "case"],
        "handler": _query_cases_impl,
        "arg_names": ["status", "page"],
    },
    {
        "name": "query_dealer_profile",
        "description": "查询经销商风险画像。参数: user_id(经销商ID,如 D002)。返回风险评分、订货统计、保修/维修次数、合同状态。",
        "keywords": ["画像", "经销商", "风险评分", "profile", "档案"],
        "handler": _query_dealer_profile_impl,
        "arg_names": ["user_id"],
    },
    {
        "name": "manage_blacklist",
        "description": "管理风控黑名单。参数: action(add/remove/check/list)、blacklist_type(经销商ID/设备SN/维修工/用户)、value(值)、reason(原因)。",
        "keywords": ["黑名单", "拉黑", "加黑", "blacklist"],
        "handler": _manage_blacklist_impl,
        "arg_names": ["action", "blacklist_type", "value", "reason"],
    },
    {
        "name": "query_dashboard_stats",
        "description": "查询仪表盘统计数据: 今日评估数、待审案件、拒绝案件、启用规则数、决策分布。",
        "keywords": ["统计", "今日", "仪表盘", "概览", "dashboard", "summary"],
        "handler": _query_dashboard_stats_impl,
        "arg_names": [],
    },
    {
        "name": "analyze_risk_trend",
        "description": "分析指定天数内的风控趋势。参数: days(天数, 默认30)。返回每日评估量、风险等级分布、决策分布。",
        "keywords": ["趋势", "走势", "近30天", "近7天", "trend", "分布"],
        "handler": _analyze_risk_trend_impl,
        "arg_names": ["days"],
    },
    {
        "name": "analyze_rule_effectiveness",
        "description": "分析所有启用规则的命中效果: 命中次数、命中率。",
        "keywords": ["规则命中", "命中率", "规则效果", "规则分析", "effectiveness"],
        "handler": _analyze_rule_effectiveness_impl,
        "arg_names": [],
    },
    {
        "name": "query_business_data",
        "description": "查询业务数据。参数: query_type(dealer_orders/dealer_info/warranty_list/report_list/order_detail/recent_orders)、dealer_id、order_id、limit。",
        "keywords": ["订单", "订货", "保修", "维修", "举报", "业务", "查询", "business"],
        "handler": _query_business_data_impl,
        "arg_names": ["query_type", "dealer_id", "order_id", "limit"],
    },
]

ALL_TOOLS = TOOL_REGISTRY


# ============================================================
# Demo: 列出 8 个工具 + 字典派发表 — 无需 DB
# 跑法: python -m app.agent.tools
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Agent Tools — 8 个制造业工具 + 注册表")
    print("=" * 60)
    print("\n[1] 8 个工具:")
    for t in TOOL_REGISTRY:
        print(f"  {t['name']:<30} keywords={t['keywords'][:3]}...")
    print("\n[2] 字典派发表:")
    print(f"  _BLACKLIST_ACTIONS  = {list(_BLACKLIST_ACTIONS.keys())}  (4 个 action)")
    print(f"  _BIZ_QUERY_HANDLERS = {list(_BIZ_QUERY_HANDLERS.keys())}  (6 个 query_type)")
    print(f"  共 {len(TOOL_REGISTRY)} 个工具")
