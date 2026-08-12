"""Router 层：对齐源码的教育风险评估历史模块。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RiskAssessment, RiskEvent
from app.routers.risk import get_session
from app.schemas import AssessmentListItem, AssessmentListResponse


assessment_router = APIRouter(prefix="/api/assessments", tags=["教育风控评估历史"])


@assessment_router.get("", response_model=AssessmentListResponse)
def list_assessments(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_session)) -> AssessmentListResponse:
    total = session.scalar(select(func.count()).select_from(RiskAssessment)) or 0
    rows = session.execute(
        select(RiskAssessment, RiskEvent)
        .join(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id)
        .order_by(RiskEvent.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AssessmentListResponse(items=[AssessmentListItem(assessment_id=assessment.assessment_id, event_id=assessment.event_id, user_id=assessment.user_id, final_score=assessment.final_score, risk_level=assessment.risk_level, decision=assessment.decision, event_type=event.event_type, source_id=event.source_id) for assessment, event in rows], total=total, page=page, page_size=page_size)
