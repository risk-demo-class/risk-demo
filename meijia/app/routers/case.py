from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models_risk import RiskCase
from app.routers.common import case_dict, page_meta
from app.schemas import CaseReviewRequest
from app.service.action_log import record_action

router = APIRouter(prefix="/api/cases", tags=["案件"])


@router.get("")
def list_cases(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: str | None = None, db: Session = Depends(get_session),
):
    conditions = [RiskCase.case_status == status] if status else []
    total = db.scalar(select(func.count()).select_from(RiskCase).where(*conditions)) or 0
    rows = list(db.scalars(select(RiskCase).where(*conditions).order_by(desc(RiskCase.created_at)).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [case_dict(db, row) for row in rows], **page_meta(total, page, page_size)}


@router.get("/statistics")
def case_statistics(db: Session = Depends(get_session)):
    values = dict(db.execute(select(RiskCase.case_status, func.count()).group_by(RiskCase.case_status)).all())
    return {"total": sum(values.values()), "by_status": values}


@router.get("/{case_id}")
def case_detail(case_id: str, db: Session = Depends(get_session)):
    row = db.get(RiskCase, case_id)
    if not row:
        raise HTTPException(404, "案件不存在")
    data = case_dict(db, row)
    data["risk_detail"] = row.risk_detail
    return data


@router.post("/{case_id}/review")
def review_case(case_id: str, data: CaseReviewRequest, db: Session = Depends(get_session), operator: str = Header(default="admin", alias="X-Operator")):
    row = db.get(RiskCase, case_id)
    if not row:
        raise HTTPException(404, "案件不存在")
    if row.case_status in ("已通过", "已拒绝", "已关闭"):
        raise HTTPException(409, "案件已经完成审核")
    before = {"case_status": row.case_status}
    row.case_status, row.reviewer = data.decision, data.reviewer
    row.review_comment, row.reviewed_at = data.review_comment, datetime.now()
    record_action(
        db, operator=operator, action_type="REVIEW_CASE", target_type="case",
        target_id=case_id, before_value=before,
        after_value={"case_status": row.case_status, "review_comment": row.review_comment},
        remark=data.review_comment or None,
    )
    db.commit()
    return case_dict(db, row)
