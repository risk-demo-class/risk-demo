"""全量风险评估历史 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import Decision, EventType, RiskLevel
from app.schemas import AssessmentDetailResponse, AssessmentListResponse
from app.service.admin import assessment_detail, list_assessments


router = APIRouter(prefix="/api/assessments", tags=["评估历史"])


@router.get("", response_model=AssessmentListResponse)
async def get_assessments(
    decision: Decision | None = None,
    risk_level: RiskLevel | None = None,
    event_type: EventType | None = None,
    user_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
) -> AssessmentListResponse:
    return await list_assessments(
        db,
        decision=decision,
        risk_level=risk_level,
        event_type=event_type,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
async def get_assessment(
    assessment_id: str,
    db: AsyncSession = Depends(get_db_async),
) -> AssessmentDetailResponse:
    result = await assessment_detail(db, assessment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="评估记录不存在")
    return result
