"""评估历史 API (银行语义, 2 个端点)"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import AssessmentDetailResponse, AssessmentListResponse
from app.service.case import get_assessment_detail, list_assessments

assessment_router = APIRouter(prefix="/api/assessments", tags=["评估历史"])


@assessment_router.get("", response_model=AssessmentListResponse)
async def api_list_assessments(
    decision: str = Query(None), risk_level: str = Query(None),
    event_type: str = Query(None), user_id: str = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    return await list_assessments(db, decision=decision, risk_level=risk_level,
        event_type=event_type, user_id=user_id, page=page, page_size=page_size)


@assessment_router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
async def api_get_assessment(assessment_id: str, db: AsyncSession = Depends(get_db_async)):
    detail = await get_assessment_detail(db, assessment_id)
    if not detail:
        raise HTTPException(404, "评估不存在")
    return detail
