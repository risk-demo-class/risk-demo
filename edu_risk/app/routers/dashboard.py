"""仪表盘统计接口"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Enrollment, PaymentRecord, RefundRecord, RiskAssessment, RiskCase, RiskEvent,
)

router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@router.get("/stats")
async def dashboard_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    """运营大盘: 检查量/决策分布/案件/业务量。"""
    since = datetime.now() - timedelta(days=days)

    total_checks = (await db.execute(select(func.count(RiskEvent.event_id)).where(
        RiskEvent.create_time >= since))).scalar() or 0

    # 决策分布
    decision_rows = (await db.execute(
        select(RiskAssessment.decision, func.count())
        .join(RiskEvent, RiskEvent.event_id == RiskAssessment.event_id)
        .where(RiskEvent.create_time >= since)
        .group_by(RiskAssessment.decision))).all()
    decision_dist = {d: c for d, c in decision_rows}

    # 待审核案件
    pending_cases = (await db.execute(select(func.count(RiskCase.case_id)).where(
        RiskCase.case_status == "待审核"))).scalar() or 0

    # 业务量
    enrollments = (await db.execute(select(func.count(Enrollment.enrollment_id)).where(
        Enrollment.create_time >= since))).scalar() or 0
    payments = (await db.execute(select(func.count(PaymentRecord.payment_id)).where(
        PaymentRecord.pay_time >= since))).scalar() or 0
    refunds = (await db.execute(select(func.count(RefundRecord.refund_id)).where(
        RefundRecord.apply_time >= since))).scalar() or 0

    return {
        "window_days": days,
        "total_checks": total_checks,
        "decision_distribution": decision_dist,
        "pending_cases": pending_cases,
        "business_volume": {
            "enrollments": enrollments,
            "payments": payments,
            "refunds": refunds,
        },
    }


@router.get("/trend")
async def risk_trend(days: int = 7, db: AsyncSession = Depends(get_db)):
    """风险趋势(按天)。"""
    since = datetime.now() - timedelta(days=days)
    rows = (await db.execute(
        select(func.date(RiskEvent.create_time), func.count())
        .where(RiskEvent.create_time >= since)
        .group_by(func.date(RiskEvent.create_time))
        .order_by(func.date(RiskEvent.create_time)))).all()
    return {"trend": [{"date": str(d), "count": c} for d, c in rows]}


@router.get("/rule-effectiveness")
async def rule_effectiveness(db: AsyncSession = Depends(get_db)):
    """规则命中率分析。"""
    from app.models import RiskFeature  # noqa
    assessments = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.hit_rules.is_not(None))
        .limit(1000))).scalars().all()
    from collections import Counter
    counter = Counter()
    for a in assessments:
        for hit in (a.hit_rules or []):
            counter[hit.get("rule_id", "?")] += 1
    total = sum(counter.values())
    return {
        "total_assessments": len(assessments),
        "rule_hits": [{"rule_id": rid, "count": c, "rate": round(c / total, 4) if total else 0}
                      for rid, c in counter.most_common(20)],
    }
