"""Analyst-facing dashboard, assessment, case and customer APIs."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.service.operations import (
    assessment_detail,
    customer_360,
    dashboard_stats,
    list_assessments,
    list_cases,
    review_case,
    rule_effectiveness,
)


router = APIRouter(prefix="/api", tags=["operations"])


class CaseReviewRequest(BaseModel):
    decision: str
    reviewer: str = Field(min_length=1, max_length=64)
    comment: str = Field(default="", max_length=1000)


@router.get("/dashboard/overview")
async def dashboard(session: AsyncSession = Depends(get_db)) -> dict:
    return await dashboard_stats(session)


@router.get("/assessments")
async def assessments(
    scenario: str | None = None,
    decision: str | None = None,
    user_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await list_assessments(
        session, scenario=scenario, decision=decision, user_id=user_id, page=page, page_size=page_size
    )


@router.get("/assessments/{assessment_id}")
async def assessment(assessment_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    result = await assessment_detail(session, assessment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return result


@router.get("/cases")
async def cases(
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await list_cases(session, status=status, page=page, page_size=page_size)


@router.post("/cases/{case_id}/review")
async def case_review(
    case_id: str,
    data: CaseReviewRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await review_case(
            session, case_id, decision=data.decision, reviewer=data.reviewer, comment=data.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="case not found")
    return result


@router.get("/customers/{user_id}")
async def customer(user_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    result = await customer_360(session, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return result


@router.get("/rules/effectiveness")
async def effectiveness(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await rule_effectiveness(session)
