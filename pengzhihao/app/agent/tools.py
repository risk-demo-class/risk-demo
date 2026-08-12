"""物流风控 AI Agent 的 8 个工具。"""
import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

import ulid
from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CORE_BLACKLIST_LABEL_TO_TYPE, CORE_RULE_CATEGORY_TO_LOGISTICS
from app.database import AsyncSessionLocal
from app.engine.feature import compute_user_features
from app.models import (
    Address, RiskAssessment, RiskBlacklist, RiskCase, RiskEvent, RiskRule,
    Shipment, ShipmentItem,
)
from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service.case import add_blacklist, check_blacklist, get_blacklist, get_case_list, get_case_statistics, get_user_profile
from app.service.event import process_event

logger = logging.getLogger(__name__)


async def _safe_call(error_label: str, impl, **kwargs) -> str:
    try:
        async with AsyncSessionLocal() as db:
            return await impl(db=db, **kwargs)
    except Exception as exc:
        error_id = f"err_{ulid.new().str.lower()[:12]}"
        logger.exception("%s失败 error_id=%s", error_label, error_id)
        return f"{error_label}失败: {exc} (error_id={error_id})"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _row_to_dict(row) -> dict:
    return {key: (value.isoformat() if isinstance(value, datetime) else float(value) if isinstance(value, Decimal) else value)
            for key, value in row._mapping.items()}


async def _risk_check_impl(*, db: AsyncSession, user_id: str, event_type: str, source_id: str) -> str:
    result = await process_event(db, RiskCheckRequest(
        event_type=event_type, source_id=source_id, user_id=user_id,
    ))
    return _json(result.model_dump(mode="json"))


async def _query_cases_impl(*, db: AsyncSession, status: str, page: int) -> str:
    result = await get_case_list(db, status=status or None, page=page)
    stats = await get_case_statistics(db)
    return _json({
        "items": [item.model_dump(mode="json") for item in result.items],
        "total": result.total,
        "statistics": stats.model_dump(),
    })


async def _query_user_profile_impl(*, db: AsyncSession, user_id: str) -> str:
    profile = await get_user_profile(db, user_id)
    if profile:
        data = profile.model_dump(mode="json")
        data["field_semantics"] = {
            "total_orders": "总运单", "total_refunds": "COD拒收次数",
            "refund_rate": "COD拒收率", "complaint_count": "实名异常标志",
        }
        return _json(data)
    return _json({"user_id": user_id, "features": await compute_user_features(db, user_id)})


async def _manage_blacklist_impl(
    *, db: AsyncSession, action: str, blacklist_type: str, value: str, reason: str,
) -> str:
    if action == "list":
        total, items = await get_blacklist(db)
        return _json({"total": total, "items": [item.model_dump(mode="json") for item in items]})
    if blacklist_type not in CORE_BLACKLIST_LABEL_TO_TYPE:
        return "核心黑名单类型应为：寄件人/收件地址/联系电话；扩展类型请使用黑名单页面"
    core_type = CORE_BLACKLIST_LABEL_TO_TYPE[blacklist_type]
    if action == "check":
        return f"{'命中' if await check_blacklist(db, core_type, value) else '未命中'}: {blacklist_type}={value}"
    if action == "add":
        result = await add_blacklist(db, BlacklistCreate(
            blacklist_type=blacklist_type, blacklist_value=value, reason=reason,
        ))
        await db.commit()
        return _json(result.model_dump(mode="json"))
    if action == "remove":
        row = (await db.execute(select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == core_type,
            RiskBlacklist.blacklist_value == value,
            RiskBlacklist.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if not row:
            return "未找到记录"
        row.deleted_at = datetime.now()
        await db.commit()
        return "已移除"
    return "action 应为 add/remove/check/list"


async def _stats_today(db: AsyncSession) -> dict:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (await db.execute(select(
        RiskAssessment.decision,
        RiskAssessment.risk_level,
        func.count(RiskAssessment.assessment_id),
    ).where(RiskAssessment.create_time >= today).group_by(
        RiskAssessment.decision, RiskAssessment.risk_level,
    ))).all()
    total = sum(int(row[2]) for row in rows)
    high = sum(int(row[2]) for row in rows if row[1] in ("高", "极高"))
    passed = sum(int(row[2]) for row in rows if row[0] == "通过")
    return {"total": total, "high_risk": high, "pass_rate": round(100 * passed / total, 2) if total else 0}


async def _stats_pending_cases(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(RiskCase).where(
        RiskCase.case_status.in_(["待审核", "审核中"])
    ))).scalar() or 0)


async def _stats_trend_7d(db: AsyncSession) -> list[dict]:
    since = datetime.now() - timedelta(days=6)
    rows = (await db.execute(select(
        func.date(RiskAssessment.create_time).label("day"),
        RiskAssessment.risk_level,
        func.count().label("total"),
    ).where(RiskAssessment.create_time >= since).group_by(
        func.date(RiskAssessment.create_time), RiskAssessment.risk_level,
    ).order_by(func.date(RiskAssessment.create_time)))).all()
    by_day: dict[str, dict[str, int | str]] = {}
    for row in rows:
        day = str(row.day)
        item = by_day.setdefault(day, {"date": day, "count": 0, "high_risk_count": 0})
        item["count"] = int(item["count"]) + int(row.total)
        if row.risk_level in ("高", "极高"):
            item["high_risk_count"] = int(item["high_risk_count"]) + int(row.total)
    return list(by_day.values())


async def _query_dashboard_stats_impl(*, db: AsyncSession) -> str:
    today = await _stats_today(db)
    pending = await _stats_pending_cases(db)
    trend = await _stats_trend_7d(db)
    rules = (await db.execute(select(RiskRule).where(RiskRule.is_enabled == 1))).scalars().all()
    rule_map = {rule.rule_id: rule for rule in rules}
    hit_counts: Counter[str] = Counter()
    snapshots = (await db.execute(
        select(RiskAssessment.rule_results).where(RiskAssessment.rule_results.is_not(None))
    )).scalars().all()
    for snapshot in snapshots:
        try:
            for hit in json.loads(snapshot or "[]"):
                if hit.get("rule_id"):
                    hit_counts[hit["rule_id"]] += 1
        except (TypeError, json.JSONDecodeError):
            continue
    top_rule_ids = [rule_id for rule_id, _ in hit_counts.most_common(5)]
    if len(top_rule_ids) < 5:
        top_rule_ids.extend(
            rule.rule_id for rule in sorted(rules, key=lambda item: item.priority, reverse=True)
            if rule.rule_id not in top_rule_ids
        )
    top_rules = [rule_map[rule_id] for rule_id in top_rule_ids[:5] if rule_id in rule_map]
    return _json({
        "today_assessments": today["total"],
        "today_high_risk": today["high_risk"],
        "pending_cases": pending,
        "pass_rate": today["pass_rate"],
        "trend_7d": trend,
        "top_rules": [{"rule_id": r.rule_id, "rule_name": r.rule_name,
                       "category": CORE_RULE_CATEGORY_TO_LOGISTICS.get(r.rule_category, r.rule_category),
                       "hit_count": hit_counts[r.rule_id]} for r in top_rules],
    })


async def _analyze_risk_trend_impl(*, db: AsyncSession, days: int) -> str:
    since = datetime.now() - timedelta(days=max(1, min(days, 365)))
    rows = (await db.execute(select(
        func.date(RiskAssessment.create_time), RiskAssessment.risk_level, func.count()
    ).where(RiskAssessment.create_time >= since).group_by(
        func.date(RiskAssessment.create_time), RiskAssessment.risk_level
    ))).all()
    return _json({"period_days": days, "rows": [list(row) for row in rows]})


async def _analyze_rule_effectiveness_impl(*, db: AsyncSession) -> str:
    rows = (await db.execute(select(RiskRule).where(RiskRule.is_enabled == 1))).scalars().all()
    return _json({"rules": [{"rule_id": r.rule_id, "name": r.rule_name,
                              "category": CORE_RULE_CATEGORY_TO_LOGISTICS.get(r.rule_category, r.rule_category),
                              "priority": r.priority} for r in rows]})


async def _query_business_data_impl(
    *, db: AsyncSession, query_type: str, user_id: str, order_id: str, limit: int,
) -> str:
    limit = max(1, min(limit, 100))
    if query_type == "user_shipments":
        stmt = select(Shipment).where(Shipment.sender_id == user_id).order_by(Shipment.create_time.desc()).limit(limit)
    elif query_type == "shipment_items":
        stmt = select(ShipmentItem).where(ShipmentItem.shipment_id == order_id).limit(limit)
    elif query_type == "user_addresses":
        stmt = select(Address).where(Address.user_id == user_id).limit(limit)
    elif query_type == "recent_cross_border":
        stmt = select(Shipment).where(Shipment.is_cross_border == 1).order_by(Shipment.create_time.desc()).limit(limit)
    elif query_type == "cod_risk":
        stmt = select(Shipment).where(Shipment.payment_type == "代收货款", Shipment.cod_status == "拒收").limit(limit)
    elif query_type == "dangerous_items":
        stmt = select(ShipmentItem).where(ShipmentItem.inspection_result.in_(["禁寄", "信息不符"])).limit(limit)
    else:
        return "query_type 可选 user_shipments/shipment_items/user_addresses/recent_cross_border/cod_risk/dangerous_items"
    rows = (await db.execute(stmt)).scalars().all()
    return _json([{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows])


@tool(description="对物流运单执行风险检查。event_type: 寄件受理/安检验视/跨境申报/代收货款")
async def risk_check(user_id: str, event_type: str, source_id: str) -> str:
    return await _safe_call("风险检查", _risk_check_impl, user_id=user_id, event_type=event_type, source_id=source_id)


@tool(description="查询物流风控案件列表和统计")
async def query_cases(status: str = "", page: int = 1) -> str:
    return await _safe_call("案件查询", _query_cases_impl, status=status, page=page)


@tool(description="查询寄件人的物流风险画像")
async def query_user_profile(user_id: str) -> str:
    return await _safe_call("画像查询", _query_user_profile_impl, user_id=user_id)


@tool(description="管理核心物流黑名单。类型: 寄件人/收件地址/联系电话")
async def manage_blacklist(action: str, blacklist_type: str = "寄件人", value: str = "", reason: str = "") -> str:
    return await _safe_call("黑名单操作", _manage_blacklist_impl, action=action, blacklist_type=blacklist_type, value=value, reason=reason)


@tool(description="查询物流风控仪表盘统计")
async def query_dashboard_stats() -> str:
    return await _safe_call("统计查询", _query_dashboard_stats_impl)


@tool(description="分析指定天数内物流风险趋势")
async def analyze_risk_trend(days: int = 30) -> str:
    return await _safe_call("趋势分析", _analyze_risk_trend_impl, days=days)


@tool(description="查询物流风控启用规则及其业务分类")
async def analyze_rule_effectiveness() -> str:
    return await _safe_call("规则分析", _analyze_rule_effectiveness_impl)


@tool(description="查询物流业务数据。支持寄件运单、物品明细、地址、跨境、COD和危险品")
async def query_business_data(query_type: str, user_id: str = "", order_id: str = "", limit: int = 10) -> str:
    return await _safe_call("业务查询", _query_business_data_impl, query_type=query_type, user_id=user_id, order_id=order_id, limit=limit)


RISK_TOOLS = [risk_check, query_cases, query_user_profile, manage_blacklist]
DATA_TOOLS = [query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness, query_business_data]
ALL_TOOLS = RISK_TOOLS + DATA_TOOLS
