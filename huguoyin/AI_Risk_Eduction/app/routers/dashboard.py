"""风控监控大屏 API."""
import json
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import (
    EduEnrollment,
    EduPayment,
    EduRefundRequest,
    RiskAssessment,
    RiskCase,
    RiskEvent,
)


dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


def _safe_int(value) -> int:
    return int(value or 0)


async def _count_rule_hits(db: AsyncSession, recent_limit: int = 500) -> list[dict]:
    rows = (await db.execute(
        select(RiskAssessment.rule_results)
        .order_by(RiskAssessment.create_time.desc())
        .limit(recent_limit)
    )).all()
    counter: Counter[str] = Counter()
    names: dict[str, str] = {}
    for row in rows:
        if not row.rule_results:
            continue
        try:
            rules = json.loads(row.rule_results)
        except (TypeError, json.JSONDecodeError):
            continue
        for rule in rules:
            rule_id = rule.get("rule_id")
            if not rule_id:
                continue
            counter[rule_id] += 1
            names[rule_id] = rule.get("rule_name") or rule_id
    return [
        {"rule_id": rule_id, "rule_name": names.get(rule_id, rule_id), "hit_count": count}
        for rule_id, count in counter.most_common(6)
    ]


async def _trend_by_data_window(db: AsyncSession, days: int = 14) -> list[dict]:
    """按数据最新日期往前取窗口, 避免演示数据不是今天导致图表空白。"""
    max_dt = (await db.execute(
        select(func.max(func.date(RiskAssessment.create_time))).select_from(RiskAssessment)
    )).scalar()
    if not max_dt:
        return []
    if isinstance(max_dt, str):
        end_date = datetime.strptime(max_dt, "%Y-%m-%d").date()
    else:
        end_date = max_dt
    start_date = end_date - timedelta(days=days - 1)

    rows = (await db.execute(
        select(
            func.date(RiskAssessment.create_time).label("dt"),
            func.count().label("total"),
            func.sum(case((RiskAssessment.risk_level.in_(["高", "极高"]), 1), else_=0)).label("high_total"),
            func.sum(case((RiskAssessment.decision == "拒绝", 1), else_=0)).label("reject_total"),
        )
        .select_from(RiskAssessment)
        .where(func.date(RiskAssessment.create_time) >= start_date)
        .group_by(func.date(RiskAssessment.create_time))
        .order_by(func.date(RiskAssessment.create_time))
    )).all()

    by_date = {
        str(row.dt): {
            "date": str(row.dt),
            "count": _safe_int(row.total),
            "high_risk_count": _safe_int(row.high_total),
            "reject_count": _safe_int(row.reject_total),
        }
        for row in rows
    }
    trend = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        trend.append(by_date.get(str(d), {
            "date": str(d),
            "count": 0,
            "high_risk_count": 0,
            "reject_count": 0,
        }))
    return trend


@dashboard_router.get("/overview")
async def api_dashboard_overview(db: AsyncSession = Depends(get_db_async)):
    overview = (await db.execute(
        select(
            func.count(RiskAssessment.assessment_id).label("total"),
            func.sum(case((RiskAssessment.risk_level == "极高", 1), else_=0)).label("critical"),
            func.sum(case((RiskAssessment.risk_level == "高", 1), else_=0)).label("high"),
            func.sum(case((RiskAssessment.decision == "拒绝", 1), else_=0)).label("rejected"),
            func.sum(case((RiskAssessment.decision == "人工审核", 1), else_=0)).label("review"),
            func.sum(case((RiskAssessment.decision == "通过", 1), else_=0)).label("passed"),
        ).select_from(RiskAssessment)
    )).first()

    case_rows = (await db.execute(
        select(RiskCase.case_status, func.count(RiskCase.case_id))
        .group_by(RiskCase.case_status)
    )).all()
    case_status = {row[0]: _safe_int(row[1]) for row in case_rows}

    category_rows = (await db.execute(
        select(RiskCase.case_category, func.count(RiskCase.case_id))
        .group_by(RiskCase.case_category)
        .order_by(func.count(RiskCase.case_id).desc())
    )).all()
    risk_categories = [
        {"name": row[0] or "未知", "count": _safe_int(row[1])}
        for row in category_rows
    ]

    enrollments = _safe_int((await db.execute(select(func.count()).select_from(EduEnrollment))).scalar())
    risky_prepay = _safe_int((await db.execute(
        select(func.count()).select_from(EduEnrollment).where(
            (EduEnrollment.prepaid_months > 3) | (EduEnrollment.prepaid_hours > 60)
        )
    )).scalar())
    funding_risk = _safe_int((await db.execute(
        select(func.count()).select_from(EduPayment).where(
            (EduPayment.supervision_account_flag == False) | (EduPayment.loan_flag == True)
        )
    )).scalar())
    low_study_refunds = _safe_int((await db.execute(
        select(func.count()).select_from(EduRefundRequest).where(
            EduRefundRequest.study_minutes_before_refund < 5
        )
    )).scalar())

    latest_rows = (await db.execute(
        select(
            RiskCase.case_id,
            RiskCase.user_id,
            RiskCase.case_status,
            RiskCase.case_category,
            RiskCase.source_id,
            RiskCase.create_time,
            RiskAssessment.final_score,
            RiskAssessment.risk_level,
        )
        .join(RiskAssessment, RiskCase.assessment_id == RiskAssessment.assessment_id)
        .order_by(RiskCase.update_time.desc(), RiskCase.create_time.desc())
        .limit(8)
    )).all()
    latest_cases = [
        {
            "case_id": row.case_id,
            "user_id": row.user_id,
            "case_status": row.case_status,
            "case_category": row.case_category,
            "source_id": row.source_id,
            "final_score": _safe_int(row.final_score),
            "risk_level": row.risk_level,
            "create_time": row.create_time.isoformat(sep=" ") if row.create_time else None,
        }
        for row in latest_rows
    ]

    total = _safe_int(overview.total if overview else 0)
    rejected = _safe_int(overview.rejected if overview else 0)
    review = _safe_int(overview.review if overview else 0)
    passed = _safe_int(overview.passed if overview else 0)
    high = _safe_int(overview.high if overview else 0)
    critical = _safe_int(overview.critical if overview else 0)
    risk_total = high + critical

    return {
        "total_assessments": total,
        "total_enrollments": enrollments,
        "risk_total": risk_total,
        "critical_risk": critical,
        "auto_rejected": rejected,
        "manual_review": review,
        "passed": passed,
        "pending_cases": case_status.get("待审核", 0),
        "rejected_cases": case_status.get("已拒绝", 0),
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "reject_rate": round(rejected / total * 100, 1) if total else 0,
        "review_rate": round(review / total * 100, 1) if total else 0,
        "risky_prepay": risky_prepay,
        "funding_risk": funding_risk,
        "low_study_refunds": low_study_refunds,
        "trend_14d": await _trend_by_data_window(db, days=14),
        "top_rules": await _count_rule_hits(db),
        "risk_categories": risk_categories,
        "latest_cases": latest_cases,
    }
