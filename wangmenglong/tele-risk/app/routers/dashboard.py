"""仪表盘 API - 为前端仪表盘提供动态数据"""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_risk import TelecomRiskAssessment, TelecomRiskCase, TelecomRiskRule

dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@dashboard_router.get("/overview")
async def api_dashboard_overview(db: AsyncSession = Depends(get_db_async)):
    """返回仪表盘统计数据 (对齐 ai_risk 接口契约)."""
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)

    # 今日评估数
    today_assessments = int((await db.execute(
        select(func.count()).select_from(TelecomRiskAssessment).where(
            TelecomRiskAssessment.create_time >= today_start
        )
    )).scalar() or 0)

    # 今日高/极高风险
    today_high = int((await db.execute(
        select(func.count()).select_from(TelecomRiskAssessment).where(
            TelecomRiskAssessment.create_time >= today_start,
            TelecomRiskAssessment.risk_level.in_(["高", "极高"]),
        )
    )).scalar() or 0)

    # 待审案件
    pending_cases = int((await db.execute(
        select(func.count()).select_from(TelecomRiskCase).where(
            TelecomRiskCase.case_status == "待审核"
        )
    )).scalar() or 0)

    # 通过率 (全量)
    total_ast = int((await db.execute(
        select(func.count()).select_from(TelecomRiskAssessment)
    )).scalar() or 0)
    pass_count = int((await db.execute(
        select(func.count()).select_from(TelecomRiskAssessment).where(
            TelecomRiskAssessment.decision == "通过"
        )
    )).scalar() or 0)
    pass_rate = round((pass_count / total_ast * 100), 1) if total_ast > 0 else 0.0

    # 近 7 天趋势
    trend_7d = []
    for i in range(6, -1, -1):
        day = today_start - timedelta(days=i)
        day_end = day + timedelta(days=1)
        cnt = int((await db.execute(
            select(func.count()).select_from(TelecomRiskAssessment).where(
                TelecomRiskAssessment.create_time >= day,
                TelecomRiskAssessment.create_time < day_end,
            )
        )).scalar() or 0)
        high_cnt = int((await db.execute(
            select(func.count()).select_from(TelecomRiskAssessment).where(
                TelecomRiskAssessment.create_time >= day,
                TelecomRiskAssessment.create_time < day_end,
                TelecomRiskAssessment.risk_level.in_(["高", "极高"]),
            )
        )).scalar() or 0)
        trend_7d.append({
            "date": day.strftime("%m-%d"),
            "count": cnt,
            "high_risk_count": high_cnt,
        })

    # 规则命中 TOP5 (从 rule_results JSON 聚合)
    assessments = (await db.execute(
        select(TelecomRiskAssessment.rule_results)
    )).scalars().all()
    counter: dict[str, int] = {}
    for raw in assessments:
        if not raw:
            continue
        try:
            rules = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(rules, list):
                for r in rules:
                    name = r.get("rule_name") or r.get("rule_id") or "未知"
                    counter[name] = counter.get(name, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue
    top_sorted = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:5]
    top_rules = [{"rule_name": name, "hit_count": count} for name, count in top_sorted]

    return {
        "today_assessments": today_assessments,
        "today_high_risk": today_high,
        "pending_cases": pending_cases,
        "pass_rate": pass_rate,
        "trend_7d": trend_7d,
        "top_rules": top_rules,
        "total_rules": int((await db.execute(
            select(func.count()).select_from(TelecomRiskRule).where(
                TelecomRiskRule.is_enabled == 1, TelecomRiskRule.deleted_at.is_(None)
            )
        )).scalar() or 0),
        "total_assessments": total_ast,
    }
