"""评估历史 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import AssessmentDetailResponse, AssessmentItem, AssessmentListResponse
from app.service.case import (
    count_assessments_tx,
    get_assessment_detail_tx,
    list_assessments_tx,
)

assessment_router = APIRouter(prefix="/api/assessments", tags=["评估历史"])


@assessment_router.get("", response_model=AssessmentListResponse)
async def api_list_assessments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    rows = await list_assessments_tx(db, page=page, page_size=page_size)
    total = await count_assessments_tx(db)
    items = []
    for a in rows:
        evt_type = await _event_type_of(db, a)
        items.append(AssessmentItem(
            assessment_id=a.assessment_id,
            event_id=a.event_id,
            user_id=a.user_id,
            event_type=evt_type or "",
            final_score=a.final_score,
            risk_level=a.risk_level,
            decision=a.decision,
            rule_count=a.rule_count,
            ml_score=float(a.ml_score) if a.ml_score is not None else None,
            ml_decision=a.ml_decision,
            create_time=a.create_time,
        ))
    return AssessmentListResponse(
        items=items, total=total, page=page, page_size=page_size,
    )


@assessment_router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
async def api_get_assessment(assessment_id: str, db: AsyncSession = Depends(get_db_async)):
    return await get_assessment_detail_tx(db, assessment_id)


async def _event_type_of(db: AsyncSession, assessment) -> str | None:
    """评估 → 事件类型 (查 risk_event). 逐条查开销可接受 (列表最多 100 条)."""
    from sqlalchemy import select
    from app.models import RiskEvent
    row = (await db.execute(
        select(RiskEvent.event_type).where(RiskEvent.event_id == assessment.event_id)
    )).first()
    return row.event_type if row else None
