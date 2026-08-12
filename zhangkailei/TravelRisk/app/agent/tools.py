"""TravelRisk AI Agent 的 8 个只读/受控工具。"""
import json
from datetime import datetime, timedelta

from langchain_core.tools import tool
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.config import settings
from app.models import (
    PassengerInfo, RiskAssessment, RiskCase, RiskRule, RiskUserProfile,
    TravelBlacklistEntry, TravelOrder, VisaApplication,
)
from app.schemas import RiskCheckRequest
from app.service.event import process_event
from app.service.action_log import record_action


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
async def risk_check(user_id: str, event_type: str, source_id: str) -> str:
    """对旅游业务事件执行实时风险检查。"""
    async with AsyncSessionLocal() as db:
        result = await process_event(db, RiskCheckRequest(
            user_id=user_id, event_type=event_type, source_id=source_id))
        return result.model_dump_json()


@tool
async def query_cases(status: str = "待审核", limit: int = 20) -> str:
    """查询旅游风控案件。"""
    async with AsyncSessionLocal() as db:
        stmt = select(RiskCase).order_by(RiskCase.create_time.desc()).limit(min(limit, 100))
        if status:
            stmt = stmt.where(RiskCase.case_status == status)
        rows = (await db.execute(stmt)).scalars().all()
        return _json([{"case_id": r.case_id, "user_id": r.user_id,
                       "status": r.case_status, "category": r.case_category} for r in rows])


@tool
async def query_user_profile(user_id: str) -> str:
    """查询旅游用户风险画像。"""
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(RiskUserProfile).where(
            RiskUserProfile.user_id == user_id))).scalar_one_or_none()
        if not row:
            return _json({"error": "用户尚无风险画像"})
        return _json({"user_id": row.user_id, "risk_score": row.risk_score,
                      "risk_level": row.risk_level, "assessment_count": row.assessment_count,
                      "profile_data": json.loads(row.profile_data or "{}")})


@tool
async def manage_travel_blacklist(action: str, entry_type: str, value: str, reason: str = "") -> str:
    """检查、添加或移除 PASSPORT/VISA/DEVICE/IP 旅游黑名单。"""
    if entry_type not in settings.TRAVEL_BLACKLIST_TYPES:
        return _json({"ok": False, "error": f"entry_type 必须是 {settings.TRAVEL_BLACKLIST_TYPES}"})
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(TravelBlacklistEntry).where(
            TravelBlacklistEntry.entry_type == entry_type,
            TravelBlacklistEntry.entry_value_hash == value,
            TravelBlacklistEntry.deleted_at.is_(None)))).scalar_one_or_none()
        if action == "check":
            return _json({"hit": bool(row), "type": entry_type})
        if action == "add":
            if not row:
                row = TravelBlacklistEntry(entry_type=entry_type,
                                           entry_value_hash=value, reason=reason)
                db.add(row)
            else:
                row.deleted_at = None
                row.reason = reason
            await db.flush()
            await record_action(db, operator="ai_agent", action_type="ADD_BLACKLIST",
                                target_type="blacklist", target_id=f"travel:{row.entry_id}",
                                after_value={"entry_type": entry_type, "entry_value_hash": value})
            await db.commit()
            return _json({"ok": True, "action": "add"})
        if action == "remove" and row:
            await record_action(db, operator="ai_agent", action_type="REMOVE_BLACKLIST",
                                target_type="blacklist", target_id=f"travel:{row.entry_id}",
                                before_value={"entry_type": entry_type, "entry_value_hash": value})
            row.deleted_at = datetime.now()
            await db.commit()
            return _json({"ok": True, "action": "remove"})
        return _json({"ok": False, "error": "action 必须是 check/add/remove"})


@tool
async def query_dashboard_stats() -> str:
    """查询今日评估、拒绝、待审核案件和规则数量。"""
    async with AsyncSessionLocal() as db:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        total = await db.scalar(select(func.count()).select_from(RiskAssessment).where(
            RiskAssessment.create_time >= today)) or 0
        high_risk = await db.scalar(select(func.count()).select_from(RiskAssessment).where(
            RiskAssessment.create_time >= today,
            RiskAssessment.decision.in_(("人工审核", "拒绝")))) or 0
        passed = await db.scalar(select(func.count()).select_from(RiskAssessment).where(
            RiskAssessment.create_time >= today, RiskAssessment.decision == "通过")) or 0
        pending = await db.scalar(select(func.count()).select_from(RiskCase).where(
            RiskCase.case_status.in_(("待审核", "审核中")))) or 0
        rules = await db.scalar(select(func.count()).select_from(RiskRule).where(
            RiskRule.is_enabled == 1, RiskRule.deleted_at.is_(None))) or 0
        since = today - timedelta(days=6)
        trend_rows = (await db.execute(select(
            func.date(RiskAssessment.create_time).label("day"),
            func.count().label("count"),
            func.sum(func.if_(RiskAssessment.decision.in_(("人工审核", "拒绝")), 1, 0)).label("high")
        ).where(RiskAssessment.create_time >= since).group_by("day").order_by("day"))).all()
        recent = (await db.execute(select(RiskAssessment.rule_results).where(
            RiskAssessment.create_time >= since).limit(500))).scalars().all()
        hit_counts: dict[str, int] = {}
        for raw in recent:
            try:
                for item in json.loads(raw or "[]"):
                    key = item.get("rule_name") or item.get("rule_id")
                    if key:
                        hit_counts[key] = hit_counts.get(key, 0) + 1
            except (json.JSONDecodeError, TypeError):
                continue
        top_rules = [{"rule_name": k, "hit_count": v} for k, v in
                     sorted(hit_counts.items(), key=lambda x: x[1], reverse=True)[:5]]
        return _json({
            "today_assessments": total,
            "today_high_risk": high_risk,
            "pending_cases": pending,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "enabled_rules": rules,
            "trend_7d": [{"date": str(d), "count": c, "high_risk_count": int(h or 0)}
                         for d, c, h in trend_rows],
            "top_rules": top_rules,
        })


@tool
async def analyze_risk_trend(days: int = 7) -> str:
    """分析最近 N 天旅游风险评估趋势。"""
    async with AsyncSessionLocal() as db:
        since = datetime.now() - timedelta(days=max(1, min(days, 90)))
        rows = (await db.execute(select(
            func.date(RiskAssessment.create_time), func.count(), func.avg(RiskAssessment.final_score)
        ).where(RiskAssessment.create_time >= since).group_by(
            func.date(RiskAssessment.create_time)).order_by(func.date(RiskAssessment.create_time)))).all()
        return _json([{"date": str(d), "count": c, "avg_score": float(a or 0)} for d, c, a in rows])


@tool
async def analyze_rule_effectiveness() -> str:
    """统计规则数量以及当前评估命中情况。"""
    async with AsyncSessionLocal() as db:
        rules = (await db.execute(select(RiskRule).where(
            RiskRule.deleted_at.is_(None)).order_by(RiskRule.priority.desc()))).scalars().all()
        return _json([{"rule_id": r.rule_id, "name": r.rule_name,
                       "enabled": bool(r.is_enabled), "score": r.risk_score} for r in rules])


@tool
async def query_travel_data(user_id: str, data_type: str = "orders", limit: int = 20) -> str:
    """查询用户的 orders、passengers 或 visas 旅游业务数据。"""
    async with AsyncSessionLocal() as db:
        limit = max(1, min(limit, 100))
        if data_type == "passengers":
            rows = (await db.execute(select(PassengerInfo).where(
                PassengerInfo.user_id == user_id).limit(limit))).scalars().all()
            return _json([{"passenger_id": r.passenger_id, "name": r.name,
                           "nationality": r.nationality} for r in rows])
        if data_type == "visas":
            rows = (await db.execute(select(VisaApplication).where(
                VisaApplication.user_id == user_id).limit(limit))).scalars().all()
            return _json([{"visa_id": r.visa_id, "country": r.dest_country,
                           "status": r.application_status} for r in rows])
        rows = (await db.execute(select(TravelOrder).where(
            TravelOrder.user_id == user_id).order_by(TravelOrder.create_time.desc()).limit(limit))).scalars().all()
        return _json([{"order_id": r.order_id, "type": r.order_type,
                       "amount": float(r.total_amount), "country": r.dest_country} for r in rows])


ALL_TOOLS = [risk_check, query_cases, query_user_profile, manage_travel_blacklist,
             query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness,
             query_travel_data]
