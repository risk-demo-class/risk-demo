from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models_business import UserInfo
from app.models_risk import RiskAssessment, RiskCase
from app.routers.common import assessment_dict

router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@router.get("/overview")
def overview(db: Session = Depends(get_session)):
    total = db.scalar(select(func.count()).select_from(RiskAssessment)) or 0
    positive = db.scalar(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.decision != "通过")) or 0
    pending = db.scalar(select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")) or 0
    users = db.scalar(select(func.count()).select_from(UserInfo)) or 0
    decision_rows = db.execute(select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)).all()
    recent = list(db.scalars(select(RiskAssessment).order_by(desc(RiskAssessment.created_at)).limit(8)))
    return {
        "assessment_count": total, "risk_count": positive,
        "risk_rate": round(positive / total, 4) if total else 0,
        "pending_cases": pending, "user_count": users,
        "decision_distribution": dict(decision_rows),
        "recent": [assessment_dict(item) for item in recent],
    }
