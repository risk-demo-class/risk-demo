"""银行风险案件管理 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_risk import CaseStatus
from app.schemas import CaseDetailResponse, CaseListResponse, CaseReviewRequest, CaseStatistics
from app.service.admin import case_detail, case_statistics, list_cases, review_case


router = APIRouter(prefix="/api/cases", tags=["案件管理"])


@router.get("", response_model=CaseListResponse)
async def get_cases(
    status: CaseStatus | None = None,
    user_id: str | None = None,
    active_only: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
) -> CaseListResponse:
    return await list_cases(
        db,
        status=status,
        user_id=user_id,
        active_only=active_only,
        page=page,
        page_size=page_size,
    )


@router.get("/statistics", response_model=CaseStatistics)
async def get_case_statistics(db: AsyncSession = Depends(get_db_async)) -> CaseStatistics:
    return await case_statistics(db)


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db_async)) -> CaseDetailResponse:
    result = await case_detail(db, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    return result


@router.post("/{case_id}/review", response_model=CaseDetailResponse)
async def post_case_review(
    case_id: str,
    data: CaseReviewRequest,
    db: AsyncSession = Depends(get_db_async),
) -> CaseDetailResponse:
    async with db.begin():
        return await review_case(db, case_id, data)
