"""案件管理 API."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import CaseDetailResponse, CaseListResponse, CaseReviewRequest, CaseStatistics
from app.service.case import (
    get_case_detail,
    get_case_statistics,
    list_cases,
    review_case,
)

router = APIRouter(prefix="/api/cases", tags=["案件"])


@router.get("", response_model=CaseListResponse)
async def api_list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db_async),
) -> CaseListResponse:
    """案件列表."""
    total, items = await list_cases(
        db,
        page=page,
        page_size=page_size,
        status=status,
        active_only=active_only,
    )
    return CaseListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=CaseStatistics)
async def api_case_stats(
    db: AsyncSession = Depends(get_db_async),
) -> CaseStatistics:
    """案件统计."""
    return await get_case_statistics(db)


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def api_get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db_async),
) -> CaseDetailResponse:
    """案件详情."""
    return await get_case_detail(db, case_id)


@router.post("/{case_id}/review", response_model=CaseDetailResponse)
async def api_review_case(
    case_id: str,
    request: CaseReviewRequest,
    db: AsyncSession = Depends(get_db_async),
) -> CaseDetailResponse:
    """案件审核."""
    result = await review_case(db, case_id, request)
    await db.commit()
    return result
