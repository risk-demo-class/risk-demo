"""仪表盘 API: 概览统计 (卡片 + 分布 + 最近评估)"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAssessment, RiskCase, RiskRule

dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@dashboard_router.get("/overview")
async def api_dashboard_overview(db: AsyncSession = Depends(get_db_async)):
    """概览数据:
      - 卡片: 今日评估数 / 待审核案件 / 拒绝案件 / 启用规则数
      - 分布: 决策分布 (通过/标记/人工审核/拒绝) + 风险等级分布
      - 最近 10 条评估
    """
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    assessments_today = int((await db.execute(
        select(func.count()).select_from(RiskAssessment).where(
            RiskAssessment.create_time >= today_start
        )
    )).scalar() or 0)

    pending_cases = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(
            RiskCase.case_status == "待审核"
        )
    )).scalar() or 0)

    rejected_cases = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(
            RiskCase.case_status == "已拒绝"
        )
    )).scalar() or 0)

    rule_count = int((await db.execute(
        select(func.count()).select_from(RiskRule).where(
            RiskRule.is_enabled == 1,
            RiskRule.deleted_at.is_(None),
        )
    )).scalar() or 0)

    # 决策分布
    decision_rows = (await db.execute(
        select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)
    )).all()
    decision_distribution = {d: int(c) for d, c in decision_rows}

    # 风险等级分布
    level_rows = (await db.execute(
        select(RiskAssessment.risk_level, func.count()).group_by(RiskAssessment.risk_level)
    )).all()
    level_distribution = {l: int(c) for l, c in level_rows}

    # 最近 10 条评估
    recent = (await db.execute(
        select(RiskAssessment)
        .order_by(RiskAssessment.create_time.desc())
        .limit(10)
    )).scalars().all()

    return {
        "assessments_today": assessments_today,
        "pending_cases": pending_cases,
        "rejected_cases": rejected_cases,
        "rule_count": rule_count,
        "decision_distribution": decision_distribution,
        "level_distribution": level_distribution,
        "recent_assessments": [
            {
                "assessment_id": a.assessment_id,
                "user_id": a.user_id,
                "final_score": a.final_score,
                "risk_level": a.risk_level,
                "decision": a.decision,
                "rule_count": a.rule_count,
                "create_time": a.create_time.isoformat() if a.create_time else None,
            }
            for a in recent
        ],
    }


@dashboard_router.get("/trend")
async def api_dashboard_trend(db: AsyncSession = Depends(get_db_async)):
    """近 7 天每日评估数趋势."""
    days = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(6, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        cnt = int((await db.execute(
            select(func.count()).select_from(RiskAssessment).where(
                RiskAssessment.create_time >= day_start,
                RiskAssessment.create_time < day_end,
            )
        )).scalar() or 0)
        days.append({"date": day_start.strftime("%m-%d"), "count": cnt})
    return {"days": days}
