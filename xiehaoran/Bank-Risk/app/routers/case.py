"""案件管理 API (银行语义, 4 个端点)"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import CaseDetailResponse, CaseListResponse, CaseReviewRequest, CaseStatistics
from app.service.case import get_case_detail, get_case_list, get_case_statistics, review_case

case_router = APIRouter(prefix="/api/cases", tags=["案件管理"])


@case_router.get("", response_model=CaseListResponse)
async def api_list_cases(
    status: str = Query(None), category: str = Query(None),
    active_only: bool = Query(False), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    return await get_case_list(db, status=status, category=category, active_only=active_only, page=page, page_size=page_size)


@case_router.get("/statistics", response_model=CaseStatistics)
async def api_case_statistics(db: AsyncSession = Depends(get_db_async)):
    return await get_case_statistics(db)


@case_router.get("/{case_id}", response_model=CaseDetailResponse)
async def api_get_case(case_id: str, db: AsyncSession = Depends(get_db_async)):
    detail = await get_case_detail(db, case_id)
    if not detail:
        raise HTTPException(404, "案件不存在")
    return detail


@case_router.post("/{case_id}/review", response_model=CaseDetailResponse)
async def api_review_case(case_id: str, data: CaseReviewRequest, db: AsyncSession = Depends(get_db_async)):
    detail = await review_case(db, case_id, data)
    if not detail:
        raise HTTPException(404, "案件不存在")
    return detail
