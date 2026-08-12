from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.risk import run_risk_check

router = APIRouter(prefix="/api/risk", tags=["风险检查"])


@router.post("/check", response_model=RiskCheckResponse)
def risk_check(data: RiskCheckRequest, db: Session = Depends(get_session)):
    return run_risk_check(db, data)
