"""案件管理接口 — 工作台"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.service import case as case_service

router = APIRouter(prefix="/api/cases", tags=["案件管理"])


class ReviewRequest(BaseModel):
    action: str = Field(..., description="approve=通过 / reject=拒绝")
    operator: str = Field(..., description="操作人")
    comment: str = Field(default="")


class ClaimRequest(BaseModel):
    operator: str = Field(..., description="领取人")


class CloseRequest(BaseModel):
    operator: str = Field(default="system")
    comment: str = Field(default="")


@router.get("")
async def list_cases(page: int = 1, page_size: int = 20, status: str | None = None,
                     user_id: str | None = None, active_only: bool = True,
                     db: AsyncSession = Depends(get_db)):
    return await case_service.list_cases(db, page, page_size, status, user_id, active_only)


@router.get("/{case_id}")
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    c = await case_service.get_case(db, case_id)
    return case_service._case_dict(c)


@router.post("/{case_id}/claim")
async def claim_case(case_id: str, payload: ClaimRequest, db: AsyncSession = Depends(get_db)):
    c = await case_service.claim_case(db, case_id, payload.operator)
    return case_service._case_dict(c)


@router.post("/{case_id}/review")
async def review_case(case_id: str, payload: ReviewRequest, db: AsyncSession = Depends(get_db)):
    c = await case_service.review_case(db, case_id, payload.action,
                                       payload.operator, payload.comment)
    return case_service._case_dict(c)


@router.post("/{case_id}/close")
async def close_case(case_id: str, payload: CloseRequest, db: AsyncSession = Depends(get_db)):
    c = await case_service.close_case(db, case_id, payload.operator, payload.comment)
    return case_service._case_dict(c)


@router.post("/auto-close")
async def auto_close(hours: int | None = None, db: AsyncSession = Depends(get_db)):
    """手动触发超时自动关闭。"""
    closed = await case_service.auto_close_timeout_cases(db, hours)
    return {"closed_count": closed}
