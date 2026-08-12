"""Agent tools - bank risk control (minimal working version)"""
import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import RiskAssessment, RiskRule, RiskCase, RiskBlacklist, RiskUserProfile


async def query_dashboard_stats() -> dict:
    """Return dashboard overview statistics."""
    try:
        db = AsyncSessionLocal()
        async with db as session:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await _count_since(session, RiskAssessment, today)
            high_risk = await _count_high_risk_since(session, today)
            pending = await _count_status(session, RiskCase, '待审核')
            total_today = await _count_since(session, RiskAssessment, today)
            pass_count = await _count_decision_since(session, '通过', today)
            pass_rate = round(pass_count / max(total_today, 1) * 100, 1)
            
            trend = await _get_trend_7d(session)
            top_rules = await _get_top_rules(session)
            
            return {
                "today_assessments": today_count,
                "today_high_risk": high_risk,
                "pending_cases": pending,
                "pass_rate": pass_rate,
                "trend_7d": trend,
                "top_rules": top_rules,
            }
    except Exception as e:
        return {"error": str(e), "today_assessments": 0, "today_high_risk": 0, "pending_cases": 0, "pass_rate": 0, "trend_7d": [], "top_rules": []}

async def _count_since(session, model, since):
    r = await session.execute(select(func.count()).select_from(model).where(model.create_time >= since))
    return r.scalar() or 0

async def _count_high_risk_since(session, since):
    r = await session.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since, RiskAssessment.risk_level.in_(["高","极高"]))
    )
    return r.scalar() or 0

async def _count_status(session, model, status):
    r = await session.execute(
        select(func.count()).select_from(model).where(model.case_status == status)
    )
    return r.scalar() or 0

async def _count_decision_since(session, decision, since):
    r = await session.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since, RiskAssessment.decision == decision)
    )
    return r.scalar() or 0

async def _get_trend_7d(session):
    results = []
    for i in range(6, -1, -1):
        day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
        next_day = day + timedelta(days=1)
        count = (await session.execute(
            select(func.count()).select_from(RiskAssessment)
            .where(RiskAssessment.create_time >= day, RiskAssessment.create_time < next_day)
        )).scalar() or 0
        high = (await session.execute(
            select(func.count()).select_from(RiskAssessment)
            .where(RiskAssessment.create_time >= day, RiskAssessment.create_time < next_day,
                   RiskAssessment.risk_level.in_(["高","极高"]))
        )).scalar() or 0
        results.append({"date": day.strftime("%m-%d"), "count": count, "high_risk_count": high})
    return results

async def _get_top_rules(session):
    r = await session.execute(
        select(RiskAssessment.rule_results).where(RiskAssessment.rule_count > 0)
        .order_by(RiskAssessment.create_time.desc()).limit(500)
    )
    counts = {}
    for row in r.scalars():
        try:
            rules = json.loads(row) if isinstance(row, str) else row
            for rule in rules:
                name = rule.get("rule_name", "unknown")
                counts[name] = counts.get(name, 0) + 1
        except Exception:
            pass
    sorted_rules = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
    return [{"rule_name": name, "hit_count": cnt} for name, cnt in sorted_rules]

# ALL_TOOLS list for chat integration
ALL_TOOLS = [query_dashboard_stats]
