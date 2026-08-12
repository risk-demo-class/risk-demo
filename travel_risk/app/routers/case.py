"""案件管理 API: 列表 / 详情 / 审核 (状态机 + 审计 + 黑名单联动)"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskCase
from app.schemas import CaseDetailResponse, CaseItem, CaseListResponse, CaseReviewRequest
from app.service.action_log import record_action
from app.service.case import validate_case_transition

logger = logging.getLogger(__name__)

case_router = APIRouter(prefix="/api/cases", tags=["案件管理"])


def _to_item(case: RiskCase) -> CaseItem:
    return CaseItem(
        case_id=case.case_id,
        assessment_id=case.assessment_id,
        user_id=case.user_id,
        case_status=case.case_status,
        case_category=case.case_category,
        source_id=case.source_id,
        event_type=case.event_type,
        reviewer=case.reviewer,
        review_comment=case.review_comment,
        review_time=case.review_time,
        create_time=case.create_time,
        update_time=case.update_time,
    )


@case_router.get("", response_model=CaseListResponse)
async def list_cases(
    page: int = 1,
    page_size: int = 10,
    status: str = "",
    user_id: str = "",
    db: AsyncSession = Depends(get_db_async),
):
    stmt = select(RiskCase)
    count_stmt = select(func.count()).select_from(RiskCase)
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
        count_stmt = count_stmt.where(RiskCase.case_status == status)
    if user_id:
        stmt = stmt.where(RiskCase.user_id == user_id)
        count_stmt = count_stmt.where(RiskCase.user_id == user_id)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    stmt = stmt.order_by(RiskCase.create_time.desc()).offset((page - 1) * page_size).limit(page_size)
    cases = (await db.execute(stmt)).scalars().all()
    return CaseListResponse(
        items=[_to_item(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@case_router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db_async)):
    case = (await db.execute(
        select(RiskCase).where(RiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail=f"案件不存在: {case_id}")
    item = _to_item(case)
    try:
        detail = json.loads(case.risk_detail) if case.risk_detail else None
    except json.JSONDecodeError:
        detail = None
    return CaseDetailResponse(**item.model_dump(), risk_detail=detail)


@case_router.post("/{case_id}/review")
async def review_case(
    case_id: str,
    body: CaseReviewRequest,
    db: AsyncSession = Depends(get_db_async),
):
    case = (await db.execute(
        select(RiskCase).where(RiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail=f"案件不存在: {case_id}")

    try:
        validate_case_transition(case.case_status, body.decision)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    before = _to_item(case).model_dump(mode="json")
    case.case_status = body.decision
    case.reviewer = body.reviewer
    case.review_comment = body.review_comment
    case.review_time = datetime.now()

    # 审核拒绝 → 自动加黑名单 (防再次下单)
    if body.decision == "已拒绝" and body.add_to_blacklist:
        from app.models import RiskBlacklist
        existing = (await db.execute(
            select(RiskBlacklist.blacklist_id).where(
                RiskBlacklist.blacklist_type == "用户",
                RiskBlacklist.blacklist_value == case.user_id,
                RiskBlacklist.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(RiskBlacklist(
                blacklist_type="用户",
                blacklist_value=case.user_id,
                reason=f"案件 {case_id} 审核拒绝",
            ))

    await record_action(
        db, body.reviewer, "REVIEW_CASE", "case", case_id,
        before_value=before,
        after_value={"case_status": body.decision, "review_comment": body.review_comment},
        remark=f"审核案件 {case_id} → {body.decision}",
    )
    await db.commit()
    return {"success": True, "case_id": case_id, "case_status": case.case_status}
