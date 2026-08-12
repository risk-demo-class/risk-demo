"""评估历史 API."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import AssessmentDetailResponse, AssessmentListResponse
from app.service.case import get_assessment_detail, list_assessments

router = APIRouter(prefix="/api/assessments", tags=["评估"])


@router.get("", response_model=AssessmentListResponse)
async def api_list_assessments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    decision: Optional[str] = None,
    risk_level: Optional[str] = None,
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_async),
) -> AssessmentListResponse:
    """评估历史."""
    total, items = await list_assessments(
        db,
        page=page,
        page_size=page_size,
        decision=decision,
        risk_level=risk_level,
        event_type=event_type,
    )
    return AssessmentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
async def api_get_assessment(
    assessment_id: str,
    db: AsyncSession = Depends(get_db_async),
) -> dict:
    """评估详情."""
    return await get_assessment_detail(db, assessment_id)
