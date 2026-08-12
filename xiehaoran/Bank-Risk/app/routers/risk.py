"""风控检查 API (银行语义)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event

risk_router = APIRouter(prefix="/api/risk", tags=["风控检查"])


@risk_router.post("/check", response_model=RiskCheckResponse)
async def api_risk_check(request: RiskCheckRequest, db: AsyncSession = Depends(get_db_async)):
    try:
        return await process_event(db, request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
