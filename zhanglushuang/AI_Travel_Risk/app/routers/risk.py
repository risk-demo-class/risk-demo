"""风控检查 API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event

router = APIRouter(prefix="/api/risk", tags=["风控"])


@router.post("/check", response_model=RiskCheckResponse)
async def api_risk_check(
    request: RiskCheckRequest,
    db: AsyncSession = Depends(get_db_async),
) -> RiskCheckResponse:
    """执行一次旅游风控检查."""
    return await process_event(db, request)
