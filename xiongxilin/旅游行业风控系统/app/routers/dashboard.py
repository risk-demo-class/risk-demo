"""仪表盘 API: 汇总风控评估量、风险趋势和规则命中排行。"""
import json
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAssessment, RiskCase


dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@dashboard_router.get("/overview")
async def api_dashboard_overview(db: AsyncSession = Depends(get_db_async)):
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = today_start - timedelta(days=6)

    total = await _count_assessments(db)
    today_assessments = await _count_assessments(db, RiskAssessment.create_time >= today_start)
    today_high_risk = await _count_assessments(
        db,
        RiskAssessment.create_time >= today_start,
        RiskAssessment.risk_level.in_(["高", "极高"]),
    )
    pending_cases = await _count_cases(db, RiskCase.case_status.in_(["待审核", "审核中"]))
    passed = await _count_assessments(db, RiskAssessment.decision.in_(["通过", "标记"]))
    rejected = await _count_assessments(db, RiskAssessment.decision == "拒绝")

    # 风控展示口径: "标记"属于放行但留痕, 与"通过"一起计入放行率。
    pass_rate = round(passed * 100 / total, 1) if total else 0
    trend_7d = await _load_trend_7d(db, seven_days_ago)
    top_rules = await _load_top_rules(db)

    return {
        "today_assessments": today_assessments,
        "today_high_risk": today_high_risk,
        "pending_cases": pending_cases,
        "pass_rate": pass_rate,
        "trend_7d": trend_7d,
        "top_rules": top_rules,
        # 兼容旧 Agent 工具返回字段，AI 助手或旧脚本仍可复用。
        "total_assessments": total,
        "recent_24h": today_assessments,
        "rejected": rejected,
    }


async def _count_assessments(db: AsyncSession, *conditions) -> int:
    stmt = select(func.count()).select_from(RiskAssessment)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_cases(db: AsyncSession, *conditions) -> int:
    stmt = select(func.count()).select_from(RiskCase)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int((await db.execute(stmt)).scalar() or 0)


async def _load_trend_7d(db: AsyncSession, seven_days_ago: datetime) -> list[dict]:
    rows = (await db.execute(
        select(
            func.date(RiskAssessment.create_time).label("date"),
            func.count().label("count"),
            func.sum(case(
                (RiskAssessment.risk_level.in_(["高", "极高"]), 1),
                else_=0,
            )).label("high_risk_count"),
        )
        .where(RiskAssessment.create_time >= seven_days_ago)
        .group_by(func.date(RiskAssessment.create_time))
        .order_by(func.date(RiskAssessment.create_time))
    )).all()

    by_date = {
        str(row.date): {
            "count": int(row.count or 0),
            "high_risk_count": int(row.high_risk_count or 0),
        }
        for row in rows
    }

    trend = []
    for offset in range(7):
        day = (seven_days_ago + timedelta(days=offset)).date().isoformat()
        item = by_date.get(day, {"count": 0, "high_risk_count": 0})
        trend.append({"date": day, **item})
    return trend


async def _load_top_rules(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(RiskAssessment.rule_results)
        .where(RiskAssessment.rule_count > 0)
        .order_by(RiskAssessment.create_time.desc())
        .limit(2000)
    )).scalars().all()

    counter: Counter[tuple[str, str]] = Counter()
    for raw in rows:
        if not raw:
            continue
        try:
            rules = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            continue
        for rule in rules or []:
            rule_id = str(rule.get("rule_id") or "")
            rule_name = str(rule.get("rule_name") or rule_id or "未知规则")
            if rule_id or rule_name:
                counter[(rule_id, rule_name)] += 1

    return [
        {"rule_id": rule_id, "rule_name": rule_name, "hit_count": hit_count}
        for (rule_id, rule_name), hit_count in counter.most_common(5)
    ]
