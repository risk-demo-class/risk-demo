"""银行风控 AI Agent 的 8 个 LangChain 工具。

工具层只负责编排已有 service/engine；所有 SQL 查询都使用参数化 SQLAlchemy，
返回数据不会包含卡号或身份证号原文。
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import ulid
from langchain_core.tools import tool
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.engine.feature import compute_user_features
from app.models import (
    BankCard,
    BankTransaction,
    DeviceFingerprint,
    LoanApplication,
    LoginLog,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskRule,
)
from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service.case import (
    add_blacklist,
    check_blacklist,
    get_blacklist,
    get_case_list,
    get_case_statistics,
    get_user_profile,
    remove_blacklist,
)
from app.service.event import process_event

logger = logging.getLogger(__name__)


async def _safe_call(error_label: str, impl, **kwargs) -> str:
    """统一管理数据库会话，并把内部异常转换为可追踪的 Agent 文本。"""
    try:
        async with AsyncSessionLocal() as db:
            return await impl(db=db, **kwargs)
    except Exception as exc:
        error_id = f"err_{ulid.new().str.lower()[:12]}"
        logger.exception("%s失败 [error_id=%s]", error_label, error_id)
        return f"{error_label}失败: {exc} (error_id={error_id})"


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, bool):
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return value


def _row_to_dict(row) -> dict:
    return {key: _json_value(value) for key, value in row._mapping.items()}


async def _risk_check_impl(
    *, db: AsyncSession, user_id: str, event_type: str, source_id: str,
) -> str:
    request = RiskCheckRequest(
        event_type=event_type, source_id=source_id, user_id=user_id, event_data={},
    )
    result = await process_event(db, request)
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


async def _query_cases_impl(*, db: AsyncSession, status: str, page: int) -> str:
    case_list = await get_case_list(db, status=status or None, page=max(1, page))
    stats = await get_case_statistics(db)
    return json.dumps({
        "cases": [item.model_dump(mode="json") for item in case_list.items],
        "total": case_list.total,
        "page": case_list.page,
        "statistics": stats.model_dump(mode="json"),
    }, ensure_ascii=False, indent=2)


async def _query_user_profile_impl(*, db: AsyncSession, user_id: str) -> str:
    profile = await get_user_profile(db, user_id)
    if profile:
        return json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)
    features = await compute_user_features(db, user_id)
    return json.dumps({
        "user_id": user_id,
        "has_profile": False,
        "computed_bank_features": features,
    }, ensure_ascii=False, indent=2)


async def _blacklist_add_impl(
    *, db: AsyncSession, blacklist_type: str, value: str, reason: str,
) -> str:
    result = await add_blacklist(db, BlacklistCreate(
        blacklist_type=blacklist_type, blacklist_value=value, reason=reason,
    ))
    await db.commit()
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


async def _blacklist_check_impl(
    *, db: AsyncSession, blacklist_type: str, value: str,
) -> str:
    blocked = await check_blacklist(db, blacklist_type, value)
    return f"{'在' if blocked else '不在'}黑名单中: {blacklist_type}={value}"


async def _blacklist_list_impl(*, db: AsyncSession) -> str:
    total, items = await get_blacklist(db)
    return json.dumps({
        "total": total,
        "items": [item.model_dump(mode="json") for item in items],
    }, ensure_ascii=False, indent=2)


async def _blacklist_remove_impl(
    *, db: AsyncSession, blacklist_type: str, value: str,
) -> str:
    row = (await db.execute(select(RiskBlacklist).where(
        RiskBlacklist.blacklist_type == blacklist_type,
        RiskBlacklist.blacklist_value == value,
        RiskBlacklist.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not row:
        return f"未找到黑名单记录: {blacklist_type}={value}"
    await remove_blacklist(db, row.blacklist_id)
    return f"已从黑名单移除: {blacklist_type}={value}"


_BLACKLIST_ACTIONS = {
    "add": _blacklist_add_impl,
    "check": _blacklist_check_impl,
    "list": _blacklist_list_impl,
    "remove": _blacklist_remove_impl,
}


async def _manage_blacklist_impl(
    *, db: AsyncSession, action: str, blacklist_type: str, value: str, reason: str,
) -> str:
    impl = _BLACKLIST_ACTIONS.get(action)
    if not impl:
        return "不支持的操作；可选 add/remove/check/list"
    if action == "list":
        return await impl(db=db)
    if not value:
        return f"{action} 操作必须提供 value"
    if action == "add":
        return await impl(db=db, blacklist_type=blacklist_type, value=value, reason=reason)
    return await impl(db=db, blacklist_type=blacklist_type, value=value)


async def _stats_today(db: AsyncSession) -> dict:
    today = datetime.now().date()
    row = (await db.execute(select(
        func.count().label("total"),
        func.sum(case((RiskAssessment.risk_level.in_(["高", "极高"]), 1), else_=0)).label("high"),
        func.sum(case((RiskAssessment.decision == "通过", 1), else_=0)).label("passed"),
    ).select_from(RiskAssessment).where(
        func.date(RiskAssessment.create_time) == today,
    ))).first()
    total = int(row.total or 0) if row else 0
    passed = int(row.passed or 0) if row else 0
    return {
        "today_assessments": total,
        "today_high_risk": int(row.high or 0) if row else 0,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
    }


async def _stats_trend(db: AsyncSession, days: int) -> list[dict]:
    days = max(1, min(days, 365))
    today = datetime.now().date()
    since = today - timedelta(days=days - 1)
    rows = (await db.execute(select(
        func.date(RiskAssessment.create_time).label("dt"),
        func.count().label("count"),
        func.sum(case((RiskAssessment.risk_level.in_(["高", "极高"]), 1), else_=0)).label("high"),
    ).select_from(RiskAssessment).where(
        func.date(RiskAssessment.create_time) >= since,
    ).group_by(func.date(RiskAssessment.create_time)).order_by(
        func.date(RiskAssessment.create_time),
    ))).all()
    by_date = {
        str(row.dt): {"count": int(row.count), "high_risk_count": int(row.high or 0)}
        for row in rows
    }
    return [
        {
            "date": str(since + timedelta(days=offset)),
            **by_date.get(str(since + timedelta(days=offset)), {"count": 0, "high_risk_count": 0}),
        }
        for offset in range(days)
    ]


async def _count_rule_hits(db: AsyncSession, recent_limit: int = 500) -> dict[str, int]:
    rows = (await db.execute(select(RiskAssessment.rule_results).order_by(
        RiskAssessment.create_time.desc(),
    ).limit(recent_limit))).all()
    counter: dict[str, int] = {}
    for row in rows:
        try:
            hits = json.loads(row.rule_results or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        for hit in hits:
            rule_id = hit.get("rule_id")
            if rule_id:
                counter[rule_id] = counter.get(rule_id, 0) + 1
    return counter


async def _query_dashboard_stats_impl(*, db: AsyncSession) -> str:
    pending = int((await db.execute(select(func.count()).select_from(RiskCase).where(
        RiskCase.case_status == "待审核",
    ))).scalar() or 0)
    hit_counter = await _count_rule_hits(db)
    names = dict((await db.execute(select(RiskRule.rule_id, RiskRule.rule_name))).all())
    top = sorted(hit_counter.items(), key=lambda item: item[1], reverse=True)[:5]
    return json.dumps({
        **await _stats_today(db),
        "pending_cases": pending,
        "trend_7d": await _stats_trend(db, 7),
        "top_rules": [
            {"rule_id": rid, "rule_name": names.get(rid, rid), "hit_count": count}
            for rid, count in top
        ],
    }, ensure_ascii=False, indent=2)


async def _analyze_risk_trend_impl(*, db: AsyncSession, days: int) -> str:
    days = max(1, min(days, 365))
    since = datetime.now().date() - timedelta(days=days)
    level_rows = (await db.execute(select(
        RiskAssessment.risk_level, func.count(),
    ).where(func.date(RiskAssessment.create_time) >= since).group_by(
        RiskAssessment.risk_level,
    ))).all()
    decision_rows = (await db.execute(select(
        RiskAssessment.decision, func.count(),
    ).where(func.date(RiskAssessment.create_time) >= since).group_by(
        RiskAssessment.decision,
    ))).all()
    return json.dumps({
        "period_days": days,
        "daily_counts": await _stats_trend(db, days),
        "risk_level_distribution": dict(level_rows),
        "decision_distribution": dict(decision_rows),
    }, ensure_ascii=False, indent=2)


async def _analyze_rule_effectiveness_impl(*, db: AsyncSession) -> str:
    total = int((await db.execute(select(func.count()).select_from(RiskAssessment))).scalar() or 0)
    rules = (await db.execute(select(RiskRule).where(
        RiskRule.is_enabled == 1, RiskRule.deleted_at.is_(None),
    ).order_by(RiskRule.priority.desc()))).scalars().all()
    hit_counter = await _count_rule_hits(db)
    return json.dumps({
        "total_assessments": total,
        "rules": [{
            "rule_id": row.rule_id,
            "rule_name": row.rule_name,
            "category": row.rule_category,
            "hit_count": hit_counter.get(row.rule_id, 0),
            "hit_rate_pct": round(hit_counter.get(row.rule_id, 0) / total * 100, 2) if total else 0,
        } for row in rules],
    }, ensure_ascii=False, indent=2)


async def _biz_user_transactions(db: AsyncSession, user_id: str, _: str, limit: int):
    return list((await db.execute(select(
        BankTransaction.txn_id, BankTransaction.txn_type, BankTransaction.amount,
        BankTransaction.channel, BankTransaction.geo, BankTransaction.success,
        BankTransaction.txn_at,
    ).where(BankTransaction.user_id == user_id).order_by(
        BankTransaction.txn_at.desc(),
    ).limit(limit))).all())


async def _biz_user_loans(db: AsyncSession, user_id: str, _: str, limit: int):
    return list((await db.execute(select(
        LoanApplication.loan_id, LoanApplication.institution_code,
        LoanApplication.amount, LoanApplication.term_months,
        LoanApplication.debt_ratio, LoanApplication.status, LoanApplication.apply_at,
    ).where(LoanApplication.user_id == user_id).order_by(
        LoanApplication.apply_at.desc(),
    ).limit(limit))).all())


async def _biz_user_logins(db: AsyncSession, user_id: str, _: str, limit: int):
    return list((await db.execute(select(
        LoginLog.login_id, LoginLog.device_id, LoginLog.ip, LoginLog.geo,
        LoginLog.success, LoginLog.failure_reason, LoginLog.login_at,
    ).where(LoginLog.user_id == user_id).order_by(
        LoginLog.login_at.desc(),
    ).limit(limit))).all())


async def _biz_user_cards(db: AsyncSession, user_id: str, _: str, limit: int):
    return list((await db.execute(select(
        BankCard.card_id, BankCard.bank_code, BankCard.card_type,
        BankCard.credit_limit, BankCard.current_balance, BankCard.status,
    ).where(BankCard.user_id == user_id).limit(limit))).all())


async def _biz_recent_transactions(db: AsyncSession, _: str, source_id: str, limit: int):
    stmt = select(
        BankTransaction.txn_id, BankTransaction.user_id, BankTransaction.txn_type,
        BankTransaction.amount, BankTransaction.channel, BankTransaction.geo,
        BankTransaction.device_id, BankTransaction.txn_at,
    )
    if source_id:
        stmt = stmt.where(BankTransaction.txn_id == source_id)
    return list((await db.execute(stmt.order_by(BankTransaction.txn_at.desc()).limit(limit))).all())


async def _biz_suspicious_devices(db: AsyncSession, _: str, source_id: str, limit: int):
    stmt = select(
        DeviceFingerprint.device_id,
        func.count(func.distinct(DeviceFingerprint.user_id)).label("linked_users"),
        func.max(DeviceFingerprint.last_seen).label("last_seen"),
    ).group_by(DeviceFingerprint.device_id).having(
        func.count(func.distinct(DeviceFingerprint.user_id)) >= 3,
    ).order_by(func.count(func.distinct(DeviceFingerprint.user_id)).desc())
    if source_id:
        stmt = stmt.where(DeviceFingerprint.device_id == source_id)
    return list((await db.execute(stmt.limit(limit))).all())


_BIZ_QUERY_HANDLERS = {
    "user_transactions": _biz_user_transactions,
    "user_loans": _biz_user_loans,
    "user_logins": _biz_user_logins,
    "user_cards": _biz_user_cards,
    "recent_transactions": _biz_recent_transactions,
    "suspicious_devices": _biz_suspicious_devices,
}


async def _query_business_data_impl(
    *, db: AsyncSession, query_type: str, user_id: str, source_id: str, limit: int,
) -> str:
    handler = _BIZ_QUERY_HANDLERS.get(query_type)
    if not handler:
        return f"不支持的查询类型，可选: {', '.join(_BIZ_QUERY_HANDLERS)}"
    rows = await handler(db, user_id, source_id, max(1, min(limit, 100)))
    return json.dumps([_row_to_dict(row) for row in rows], ensure_ascii=False, indent=2)


@tool(description="执行银行事件风险检查。event_type 仅可为信用卡/贷款/转账/登录；source_id 是对应业务表主键。")
async def risk_check(user_id: str, event_type: str, source_id: str) -> str:
    return await _safe_call("风险检查", _risk_check_impl,
                            user_id=user_id, event_type=event_type, source_id=source_id)


@tool(description="查询风控案件及案件统计，status 可为待审核/审核中/已通过/已拒绝/已关闭。")
async def query_cases(status: str = "", page: int = 1) -> str:
    return await _safe_call("案件查询", _query_cases_impl, status=status, page=page)


@tool(description="查询客户风险画像；未形成画像时实时计算客户层银行特征。")
async def query_user_profile(user_id: str) -> str:
    return await _safe_call("用户画像查询", _query_user_profile_impl, user_id=user_id)


@tool(description="管理运营黑名单。action=add/remove/check/list；类型为用户/设备指纹/IP/银行卡号/身份证号。")
async def manage_blacklist(
    action: str, blacklist_type: str = "用户", value: str = "", reason: str = "",
) -> str:
    return await _safe_call("黑名单操作", _manage_blacklist_impl,
                            action=action, blacklist_type=blacklist_type, value=value, reason=reason)


@tool(description="查询今日风险指标、待审案件、7 天趋势与规则命中 TOP5。")
async def query_dashboard_stats() -> str:
    return await _safe_call("统计查询", _query_dashboard_stats_impl)


@tool(description="分析指定天数内的评估量、风险等级和决策分布。")
async def analyze_risk_trend(days: int = 30) -> str:
    return await _safe_call("趋势分析", _analyze_risk_trend_impl, days=days)


@tool(description="分析全部启用规则的命中次数与命中率。")
async def analyze_rule_effectiveness() -> str:
    return await _safe_call("规则效果分析", _analyze_rule_effectiveness_impl)


@tool(description="查询银行业务数据。query_type 可为 user_transactions/user_loans/user_logins/user_cards/recent_transactions/suspicious_devices。")
async def query_business_data(
    query_type: str, user_id: str = "", source_id: str = "", limit: int = 10,
) -> str:
    return await _safe_call("业务数据查询", _query_business_data_impl,
                            query_type=query_type, user_id=user_id, source_id=source_id, limit=limit)


RISK_TOOLS = [risk_check, query_cases, query_user_profile, manage_blacklist]
DATA_TOOLS = [query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness, query_business_data]
ALL_TOOLS = RISK_TOOLS + DATA_TOOLS
