from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models_risk import RiskAssessment, RiskEvent
from app.routers.common import assessment_dict, page_meta

router = APIRouter(prefix="/api/assessments", tags=["评估"])


@router.get("")
def list_assessments(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    decision: str | None = None, user_id: str | None = None,
    db: Session = Depends(get_session),
):
    conditions = []
    if decision:
        conditions.append(RiskAssessment.decision == decision)
    if user_id:
        conditions.append(RiskAssessment.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(RiskAssessment).where(*conditions)) or 0
    rows = list(db.scalars(select(RiskAssessment).where(*conditions).order_by(desc(RiskAssessment.created_at)).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [assessment_dict(row) for row in rows], **page_meta(total, page, page_size)}


@router.get("/{assessment_id}")
def assessment_detail(assessment_id: str, db: Session = Depends(get_session)):
    row = db.get(RiskAssessment, assessment_id)
    if not row:
        raise HTTPException(404, "评估不存在")
    event = db.get(RiskEvent, row.event_id)
    data = assessment_dict(row)
    data.update({
        "features": row.feature_snapshot, "triggered_rules": row.rule_results,
        "event": {
            "event_type": event.event_type, "source_id": event.event_source_id,
            "occurred_at": event.occurred_at, "event_data": event.event_data,
        } if event else None,
    })
    return data
