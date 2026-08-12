from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.engine.feature import compute_account_features
from app.models_business import OrderInfo, RefundRequest, UserInfo
from app.models_risk import RiskAssessment
from app.routers.common import assessment_dict

router = APIRouter(prefix="/api/users", tags=["用户画像"])


@router.get("")
def list_users(q: str | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_session)):
    stmt = select(UserInfo)
    if q:
        stmt = stmt.where(or_(
            UserInfo.user_id.like(f"%{q}%"), UserInfo.name.like(f"%{q}%"),
            UserInfo.student_id.like(f"%{q}%"),
        ))
    rows = list(db.scalars(stmt.order_by(desc(UserInfo.register_at)).limit(limit)))
    return {"items": [{
        "user_id": row.user_id, "name": row.name, "role": row.role,
        "student_id": row.student_id, "real_name_status": row.real_name_status,
        "register_at": row.register_at,
    } for row in rows]}


@router.get("/{user_id}/profile")
def user_profile(user_id: str, db: Session = Depends(get_session)):
    user = db.get(UserInfo, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    features = compute_account_features(db, user_id)
    orders = db.scalar(select(func.count()).select_from(OrderInfo).where(OrderInfo.user_id == user_id)) or 0
    refunds = db.scalar(
        select(func.count()).select_from(RefundRequest)
        .join(OrderInfo, OrderInfo.order_id == RefundRequest.order_id)
        .where(OrderInfo.user_id == user_id, RefundRequest.refund_status == "退款成功")
    ) or 0
    latest = db.scalar(select(RiskAssessment).where(RiskAssessment.user_id == user_id).order_by(desc(RiskAssessment.created_at)).limit(1))
    return {
        "user": {
            "user_id": user.user_id, "name": user.name, "role": user.role,
            "student_id": user.student_id, "real_name_status": user.real_name_status,
            "register_at": user.register_at,
        },
        "metrics": {"orders": orders, "successful_refunds": refunds, **features},
        "latest_assessment": assessment_dict(latest) if latest else None,
    }
