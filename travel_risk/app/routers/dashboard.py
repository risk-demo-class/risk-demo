"""仪表盘统计 API"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import (
    BookingInfo,
    ClaimInfo,
    ComplaintInfo,
    RefundChange,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskRule,
)


dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@dashboard_router.get("/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db_async)):
    """首页统计: 业务规模 + 风控运行概况"""
    total_bookings = int((await db.execute(select(func.count()).select_from(BookingInfo))).scalar() or 0)
    total_amount = float((await db.execute(
        select(func.coalesce(func.sum(BookingInfo.traveler_count), 0)).select_from(BookingInfo)
    )).scalar() or 0)
    total_refunds = int((await db.execute(select(func.count()).select_from(RefundChange))).scalar() or 0)
    total_claims = int((await db.execute(select(func.count()).select_from(ClaimInfo))).scalar() or 0)
    total_complaints = int((await db.execute(select(func.count()).select_from(ComplaintInfo))).scalar() or 0)

    enabled_rules = int((await db.execute(
        select(func.count()).select_from(RiskRule).where(RiskRule.is_enabled == 1, RiskRule.deleted_at.is_(None))
    )).scalar() or 0)
    assessments = int((await db.execute(select(func.count()).select_from(RiskAssessment))).scalar() or 0)
    pending_cases = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status.in_(["待审核", "审核中"]))
    )).scalar() or 0)
    blacklist_count = int((await db.execute(
        select(func.count()).select_from(RiskBlacklist).where(RiskBlacklist.deleted_at.is_(None))
    )).scalar() or 0)

    # 决策分布
    decision_rows = (await db.execute(
        select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)
    )).all()
    decisions = {d: int(c) for d, c in decision_rows}

    return {
        "total_bookings": total_bookings,
        "total_travelers": int(total_amount),
        "total_refunds": total_refunds,
        "total_claims": total_claims,
        "total_complaints": total_complaints,
        "enabled_rules": enabled_rules,
        "assessments": assessments,
        "pending_cases": pending_cases,
        "blacklist_count": blacklist_count,
        "decisions": decisions,
    }
