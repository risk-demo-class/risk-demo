"""案件管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import (
    CaseDetailResponse,
    CaseItem,
    CaseListResponse,
    CaseReviewRequest,
    CaseStatistics,
)
from app.service.case import (
    count_cases_tx,
    get_case_detail_tx,
    get_case_statistics_tx,
    list_cases_tx,
    review_case_atomic,
)

case_router = APIRouter(prefix="/api/cases", tags=["案件管理"])


@case_router.get("", response_model=CaseListResponse)
async def api_list_cases(
    status: str = Query(None, description="按状态筛选: 待审核/审核中/已通过/已拒绝/已关闭"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    cases = await list_cases_tx(db, status=status, page=page, page_size=page_size)
    total = await count_cases_tx(db, status=status)
    return CaseListResponse(
        items=[CaseItem(
            case_id=c.case_id,
            assessment_id=c.assessment_id,
            user_id=c.user_id,
            case_status=c.case_status,
            case_category=c.case_category,
            create_time=c.create_time,
            source_id=c.source_id,
            event_type=c.event_type,
        ) for c in cases],
        total=total, page=page, page_size=page_size,
    )


@case_router.get("/statistics", response_model=CaseStatistics)
async def api_case_statistics(db: AsyncSession = Depends(get_db_async)):
    return await get_case_statistics_tx(db)


@case_router.get("/{case_id}", response_model=CaseDetailResponse)
async def api_get_case(case_id: str, db: AsyncSession = Depends(get_db_async)):
    return await get_case_detail_tx(db, case_id)


@case_router.post("/{case_id}/review", response_model=CaseDetailResponse)
async def api_review_case(
    case_id: str, request: CaseReviewRequest, db: AsyncSession = Depends(get_db_async),
):
    return await review_case_atomic(db, case_id, request)
