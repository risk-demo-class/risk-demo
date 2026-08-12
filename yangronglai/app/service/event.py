"""Unified risk-event entry point."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import decision_engine
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.features import feature_service


async def process_event(
    request: RiskCheckRequest,
    session: AsyncSession,
) -> RiskCheckResponse:
    context = await feature_service.build(request, session)
    return await decision_engine.assess(request, context, session)
