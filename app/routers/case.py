"""Router 层：对齐源码的教育风险案件管理模块。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RiskCase
from app.routers.risk import get_session
from app.schemas import CaseListItem, CaseListResponse, CaseReviewRequest
from app.service.case import review_case


case_router = APIRouter(prefix="/api/cases", tags=["教育风控案件"])


@case_router.get("", response_model=CaseListResponse)
def list_cases(
    case_status: str | None = Query(default=None, alias="status"),
    active_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> CaseListResponse:
    filters = []
    if case_status:
        filters.append(RiskCase.case_status == case_status)
    elif active_only:
        filters.append(RiskCase.case_status.in_(("待审核", "审核中")))
    total = session.scalar(select(func.count()).select_from(RiskCase).where(*filters)) or 0
    cases = session.scalars(
        select(RiskCase).where(*filters).order_by(RiskCase.case_id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return CaseListResponse(
        items=[CaseListItem.model_validate(case, from_attributes=True) for case in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@case_router.post("/{case_id}/review", response_model=CaseListItem)
def review_case_status(
    case_id: str, data: CaseReviewRequest, session: Session = Depends(get_session)
) -> CaseListItem:
    try:
        item = review_case(session, case_id, data.decision)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="案件不存在")
    return CaseListItem.model_validate(item, from_attributes=True)
