"""
AI Agent 工具集 (银行语义, 8 个 LangChain @tool).

风控决策工具 (RISK_TOOLS, 4): 风险检查 / 案件查询 / 用户画像 / 黑名单管理
数据分析工具 (DATA_TOOLS, 4): 仪表盘统计 / 趋势 / 规则效果 / 业务数据

业务实现是 _impl 函数, @tool 包装层只负责转 LLM 入参 → 调 _safe_call → _impl.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

from langchain_core.tools import tool
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BANK_EVENT_TYPES, BLACKLIST_TYPE_KEYS
from app.database import AsyncSessionLocal
from app.models_risk import RiskAssessment, RiskBlacklist, RiskCase, RiskRule
from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service.case import (
    add_blacklist, check_blacklist, get_blacklist, get_case_list,
    get_case_statistics, get_user_profile, remove_blacklist,
)
from app.service.event import process_event

logger = logging.getLogger(__name__)


async def _safe_call(error_label: str, impl, **kwargs) -> str:
    try:
        async with AsyncSessionLocal() as db:
            return await impl(db=db, **kwargs)
    except Exception as e:
        error_id = f"err_{uuid.uuid4().hex[:12]}"
        logger.exception("%s 执行失败 [error_id=%s]", error_label, error_id)
        return f"{error_label}失败: {e} (error_id={error_id})"


def _row_to_dict(row) -> dict:
    item = {}
    for key, val in row._mapping.items():
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "__float__"):
            val = float(val)
        item[key] = val
    return item


# ============================================================
# 风控决策工具 (4 个)
# ============================================================
async def _risk_check_impl(*, db: AsyncSession, user_id: str, event_type: str, source_id: str) -> str:
    request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id)
    result = await process_event(db, request)
    return json.dumps({
        "assessment_id": result.assessment_id, "user_id": result.user_id,
        "final_score": result.final_score, "risk_level": result.risk_level,
        "decision": result.decision, "rule_count": result.rule_count,
        "triggered_rules": [r.model_dump() for r in result.triggered_rules],
    }, ensure_ascii=False, indent=2)


async def _query_cases_impl(*, db: AsyncSession, status: str, page: int) -> str:
    case_list = await get_case_list(db, status=status or None, page=page)
    stats = await get_case_statistics(db)
    return json.dumps({
        "cases": [item.model_dump(mode="json") for item in case_list.items],
        "total": case_list.total, "page": case_list.page,
        "statistics": stats.model_dump(),
    }, ensure_ascii=False, indent=2)


async def _query_user_profile_impl(*, db: AsyncSession, user_id: str) -> str:
    profile = await get_user_profile(db, user_id)
    if not profile:
        return json.dumps({"user_id": user_id, "has_profile": False}, ensure_ascii=False, indent=2)
    return json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)


async def _blacklist_add_impl(*, db: AsyncSession, blacklist_type: str, value: str, reason: str) -> str:
    if blacklist_type not in BLACKLIST_TYPE_KEYS:
        return f"不支持的黑名单类型: {blacklist_type}, 可选: {', '.join(BLACKLIST_TYPE_KEYS)}"
    result = await add_blacklist(db, BlacklistCreate(blacklist_type=blacklist_type, blacklist_value=value, reason=reason))
    await db.commit()
    return f"已添加到黑名单: {result.model_dump(mode='json')}"


async def _blacklist_check_impl(*, db: AsyncSession, blacklist_type: str, value: str) -> str:
    is_blocked = await check_blacklist(db, blacklist_type, value)
    return f"{'在' if is_blocked else '不在'}黑名单中: {blacklist_type}={value}"


async def _blacklist_list_impl(*, db: AsyncSession) -> str:
    total, items = await get_blacklist(db)
    return json.dumps({"total": total, "items": [b.model_dump(mode="json") for b in items]},
                       ensure_ascii=False, indent=2)


async def _blacklist_remove_impl(*, db: AsyncSession, blacklist_type: str, value: str) -> str:
    bl = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == blacklist_type,
            RiskBlacklist.blacklist_value == value,
            RiskBlacklist.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not bl:
        return f"未找到黑名单记录: {blacklist_type}={value}"
    ok = await remove_blacklist(db, bl.blacklist_id)
    if not ok:
        return f"未找到黑名单记录: {blacklist_type}={value} (已被并发移除)"
    return f"已从黑名单移除: {blacklist_type}={value}"


_BLACKLIST_ACTIONS = {"add": _blacklist_add_impl, "check": _blacklist_check_impl,
                      "list": _blacklist_list_impl, "remove": _blacklist_remove_impl}
_BLACKLIST_TYPE_REQUIRED = {"add", "check", "remove"}


async def _manage_blacklist_impl(*, db: AsyncSession, action: str, blacklist_type: str, value: str, reason: str) -> str:
    impl = _BLACKLIST_ACTIONS.get(action)
    if not impl:
        return f"不支持的操作: {action}, 请使用 add/remove/check/list"
    kwargs: dict = {"db": db}
    if action in _BLACKLIST_TYPE_REQUIRED:
        kwargs["blacklist_type"] = blacklist_type
    if action in ("add", "check", "remove"):
        kwargs["value"] = value
    if action == "add":
        kwargs["reason"] = reason
    return await impl(**kwargs)


# ============================================================
# 数据分析工具 (4 个)
# ============================================================
async def _stats_today(db: AsyncSession) -> dict:
    today = datetime.now().date()
    row = (await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((RiskAssessment.risk_level.in_(["高", "极高"]), 1), else_=0)).label("high_risk"),
            func.sum(case((RiskAssessment.decision == "pass", 1), else_=0)).label("passed"),
        ).select_from(RiskAssessment).where(func.date(RiskAssessment.create_time) == today)
    )).first()
    total = int(row.total) if row and row.total else 0
    high_risk = int(row.high_risk) if row and row.high_risk else 0
    passed = int(row.passed) if row and row.passed else 0
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0
    return {"today_assessments": total, "today_high_risk": high_risk, "pass_rate": pass_rate}


async def _stats_pending_cases(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    )).scalar() or 0)


async def _stats_risk_level_distribution(db: AsyncSession) -> list[dict]:
    today = datetime.now().date()
    rows = (await db.execute(
        select(RiskAssessment.risk_level, func.count().label("cnt"))
        .select_from(RiskAssessment)
        .where(func.date(RiskAssessment.create_time) == today)
        .group_by(RiskAssessment.risk_level)
    )).all()
    order = {"低": 0, "中": 1, "高": 2, "极高": 3}
    return sorted(
        [{"level": r.risk_level, "count": int(r.cnt)} for r in rows],
        key=lambda x: order.get(x["level"], 99))


async def _stats_decision_distribution(db: AsyncSession) -> list[dict]:
    today = datetime.now().date()
    rows = (await db.execute(
        select(RiskAssessment.decision, func.count().label("cnt"))
        .select_from(RiskAssessment)
        .where(func.date(RiskAssessment.create_time) == today)
        .group_by(RiskAssessment.decision)
    )).all()
    order = {"pass": 0, "review": 1, "reject": 2, "freeze": 3, "report": 4}
    return sorted(
        [{"decision": r.decision, "count": int(r.cnt)} for r in rows],
        key=lambda x: order.get(x["decision"], 99))


async def _stats_trend_7d(db: AsyncSession) -> list[dict]:
    seven_days_ago = datetime.now().date() - timedelta(days=7)
    rows = (await db.execute(
        select(func.date(RiskAssessment.create_time).label("dt"), func.count().label("cnt"),
               func.sum(case((RiskAssessment.risk_level.in_(["高", "极高"]), 1), else_=0)).label("high_cnt"))
        .select_from(RiskAssessment).where(func.date(RiskAssessment.create_time) >= seven_days_ago)
        .group_by(func.date(RiskAssessment.create_time)).order_by(func.date(RiskAssessment.create_time))
    )).all()
    return [{"date": str(r.dt), "count": int(r.cnt), "high_risk_count": int(r.high_cnt or 0)} for r in rows]


async def _count_rule_hits(db: AsyncSession, recent_limit: int = 500) -> dict[str, int]:
    rows = (await db.execute(
        select(RiskAssessment.rule_results).order_by(RiskAssessment.create_time.desc()).limit(recent_limit)
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
    return counter


async def _enrich_with_rule_names(db: AsyncSession, rule_ids: list[str]) -> dict[str, str]:
    if not rule_ids:
        return {}
    rows = (await db.execute(
        select(RiskRule.rule_id, RiskRule.rule_name).where(RiskRule.rule_id.in_(rule_ids))
    )).all()
    return {r.rule_id: r.rule_name for r in rows}


async def _parse_top_rules(db: AsyncSession, recent_limit: int = 500, top_n: int = 5) -> list[dict]:
    counter = await _count_rule_hits(db, recent_limit)
    top = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
    names = await _enrich_with_rule_names(db, [rid for rid, _ in top])
    return [{"rule_id": rid, "rule_name": names.get(rid, rid), "hit_count": cnt} for rid, cnt in top]


async def _query_dashboard_stats_impl(*, db: AsyncSession) -> str:
    today = await _stats_today(db)
    pending = await _stats_pending_cases(db)
    trend = await _stats_trend_7d(db)
    top_rules = await _parse_top_rules(db)
    risk_level_dist = await _stats_risk_level_distribution(db)
    decision_dist = await _stats_decision_distribution(db)
    return json.dumps({
        **today,
        "pending_cases": pending,
        "trend_7d": trend,
        "top_rules": top_rules,
        "risk_level_distribution": risk_level_dist,
        "decision_distribution": decision_dist,
    }, ensure_ascii=False, indent=2)


async def _analyze_risk_trend_impl(*, db: AsyncSession, days: int) -> str:
    since = datetime.now().date() - timedelta(days=days)
    daily = (await db.execute(
        select(func.date(RiskAssessment.create_time).label("dt"), func.count().label("cnt"))
        .select_from(RiskAssessment).where(func.date(RiskAssessment.create_time) >= since)
        .group_by(func.date(RiskAssessment.create_time)).order_by(func.date(RiskAssessment.create_time))
    )).all()
    level_dist = dict((await db.execute(
        select(RiskAssessment.risk_level, func.count().label("cnt")).select_from(RiskAssessment)
        .where(func.date(RiskAssessment.create_time) >= since).group_by(RiskAssessment.risk_level)
    )).all())
    decision_dist = dict((await db.execute(
        select(RiskAssessment.decision, func.count().label("cnt")).select_from(RiskAssessment)
        .where(func.date(RiskAssessment.create_time) >= since).group_by(RiskAssessment.decision)
    )).all())
    return json.dumps({
        "period_days": days,
        "daily_counts": [{"date": str(r.dt), "count": r.cnt} for r in daily],
        "risk_level_distribution": level_dist, "decision_distribution": decision_dist,
    }, ensure_ascii=False, indent=2)


async def _analyze_rule_effectiveness_impl(*, db: AsyncSession) -> str:
    total = (await db.execute(select(func.count()).select_from(RiskAssessment))).scalar() or 0
    enabled_rules = (await db.execute(
        select(RiskRule).where(RiskRule.is_enabled == 1).order_by(RiskRule.priority.desc())
    )).scalars().all()
    hit_counter = await _count_rule_hits(db, recent_limit=500)
    rules_stats = [{
        "rule_id": r.rule_id, "rule_name": r.rule_name, "category": r.rule_category,
        "score": r.risk_score, "hit_count": hit_counter.get(r.rule_id, 0),
        "hit_rate_pct": round(hit_counter.get(r.rule_id, 0) / total * 100, 2) if total > 0 else 0,
    } for r in enabled_rules]
    return json.dumps({"total_assessments": total, "rules": rules_stats}, ensure_ascii=False, indent=2)


# ============================================================
# @tool 包装层 (8 个)
# ============================================================
@tool(description=(
    "对指定用户和银行事件执行实时风控检查。"
    "参数: user_id (用户ID)、event_type (事件类型, 可选值: transfer/loan_apply/card_txn/repay/login)、"
    "source_id (关联业务ID, 如交易流水号)。返回: 风控评估结果 (评分/等级/决策/命中规则)。"
))
async def risk_check(user_id: str, event_type: str, source_id: str) -> str:
    return await _safe_call("风险检查", _risk_check_impl, user_id=user_id, event_type=event_type, source_id=source_id)


@tool(description="查询风控案件列表。参数: status (待审核/审核中/已通过/已拒绝/已关闭, 为空查全部)、page (页码)。返回: 案件列表+统计。")
async def query_cases(status: str = "", page: int = 1) -> str:
    return await _safe_call("案件查询", _query_cases_impl, status=status, page=page)


@tool(description="查询用户的风险画像。参数: user_id (用户ID)。返回: 风险评分/交易统计/历史评估等。")
async def query_user_profile(user_id: str) -> str:
    return await _safe_call("用户画像查询", _query_user_profile_impl, user_id=user_id)


@tool(description=(
    "管理银行风控黑名单。参数: action (add/remove/check/list)、"
    "blacklist_type (account/device/ip/phone/id_card/merchant/beneficiary)、value (值)、reason (加黑原因)。"
))
async def manage_blacklist(action: str, blacklist_type: str = "account", value: str = "", reason: str = "") -> str:
    return await _safe_call("黑名单操作", _manage_blacklist_impl,
                            action=action, blacklist_type=blacklist_type, value=value, reason=reason)


@tool(description="查询风控仪表盘统计 (今日评估/高风险/待审/通过率/7天趋势/规则TOP5)。返回 JSON。")
async def query_dashboard_stats() -> str:
    return await _safe_call("统计查询", _query_dashboard_stats_impl)


@tool(description="分析指定天数内的风控趋势。参数: days (默认30)。返回: 每日评估量/风险分布/决策分布。")
async def analyze_risk_trend(days: int = 30) -> str:
    return await _safe_call("趋势分析", _analyze_risk_trend_impl, days=days)


@tool(description="分析所有启用规则的命中效果 (命中次数/命中率)。返回 JSON。")
async def analyze_rule_effectiveness() -> str:
    return await _safe_call("规则效果分析", _analyze_rule_effectiveness_impl)


@tool(description="业务数据查询占位 (银行域暂无独立业务表, 返回提示)。")
async def query_business_data(query_type: str, user_id: str = "", order_id: str = "", limit: int = 10) -> str:
    return json.dumps({"hint": "银行域事件本身即风控对象, 业务数据可通过风险检查/评估历史获取",
                       "query_type": query_type}, ensure_ascii=False)


RISK_TOOLS = [risk_check, query_cases, query_user_profile, manage_blacklist]
DATA_TOOLS = [query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness, query_business_data]
ALL_TOOLS = RISK_TOOLS + DATA_TOOLS
