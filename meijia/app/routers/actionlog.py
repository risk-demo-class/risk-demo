"""操作审计日志 API (P4-L1): 查看规则/案件/黑名单的操作留痕。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models_risk import RiskActionLog
from app.routers.common import page_meta

router = APIRouter(prefix="/api/action-logs", tags=["审计日志"])


@router.get("")
def list_action_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action_type: str | None = None,
    target_type: str | None = None,
    db: Session = Depends(get_session),
):
    conditions = []
    if action_type:
        conditions.append(RiskActionLog.action_type == action_type)
    if target_type:
        conditions.append(RiskActionLog.target_type == target_type)
    total = db.scalar(select(func.count()).select_from(RiskActionLog).where(*conditions)) or 0
    stmt = select(RiskActionLog).where(*conditions).order_by(desc(RiskActionLog.create_time))
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    items = [{
        "log_id": r.log_id, "operator": r.operator, "action_type": r.action_type,
        "target_type": r.target_type, "target_id": r.target_id,
        "before_value": r.before_value, "after_value": r.after_value,
        "ip": r.ip, "remark": r.remark, "create_time": r.create_time,
    } for r in rows]
    return {"items": items, **page_meta(total, page, page_size)}