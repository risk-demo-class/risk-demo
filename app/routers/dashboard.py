"""Router 层：沿用源码的教育风控仪表盘概览接口。"""

import json
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RiskAssessment, RiskCase, RiskEvent
from app.routers.risk import get_session


dashboard_router = APIRouter(prefix="/api/dashboard", tags=["教育风控仪表盘"])


@dashboard_router.get("/overview")
def get_dashboard_overview(session: Session = Depends(get_session)) -> dict[str, object]:
    """基于已落库的评估、事件、案件与规则快照生成运营概览。"""
    assessment_events = session.execute(
        select(RiskAssessment, RiskEvent).join(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id)
    ).all()
    today = date.today()
    dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    trend = {item: {"count": 0, "high_risk_count": 0} for item in dates}
    top_rules: Counter[tuple[str, str]] = Counter()
    today_assessments = 0
    today_high_risk = 0
    pass_count = 0

    for assessment, event in assessment_events:
        event_day = event.create_time.date()
        if event_day == today:
            today_assessments += 1
            if assessment.risk_level == "高风险":
                today_high_risk += 1
        if assessment.decision == "通过":
            pass_count += 1
        if event_day in trend:
            trend[event_day]["count"] += 1
            if assessment.risk_level == "高风险":
                trend[event_day]["high_risk_count"] += 1
        try:
            rule_results = json.loads(assessment.rule_results)
        except json.JSONDecodeError:
            rule_results = []
        for rule in rule_results:
            rule_id = rule.get("rule_id")
            rule_name = rule.get("rule_name")
            if rule_id and rule_name:
                top_rules[(rule_id, rule_name)] += 1

    pending_cases = session.scalar(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    ) or 0
    return {
        "today_assessments": today_assessments,
        "today_high_risk": today_high_risk,
        "pending_cases": pending_cases,
        "pass_rate": round(pass_count * 100 / len(assessment_events)) if assessment_events else 0,
        "trend_7d": [{"date": item.isoformat(), **trend[item]} for item in dates],
        "top_rules": [
            {"rule_id": rule_id, "rule_name": rule_name, "hit_count": hit_count}
            for (rule_id, rule_name), hit_count in top_rules.most_common(5)
        ],
    }
