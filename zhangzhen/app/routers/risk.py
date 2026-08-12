"""实时风险检查 HTTP 入口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event


router = APIRouter(prefix="/api/risk", tags=["实时风险检查"])


@router.post("/check", response_model=RiskCheckResponse, summary="执行银行风险检查")
async def check_risk(
    request: RiskCheckRequest,
    db: AsyncSession = Depends(get_db_async),
) -> RiskCheckResponse:
    return await process_event(db, request)

