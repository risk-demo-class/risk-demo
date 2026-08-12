"""风控检查 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.routers.education import is_education_risk_request, process_education_risk_check
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event


risk_router = APIRouter(prefix="/api/risk", tags=["风控检查"])


@risk_router.post("/check", response_model=RiskCheckResponse)
async def api_risk_check(request: RiskCheckRequest, db: AsyncSession = Depends(get_db_async)):
    if is_education_risk_request(request):
        return await process_education_risk_check(db, request)
    return await process_event(db, request)
