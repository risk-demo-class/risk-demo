"""一次银行风险事件的四步业务编排。"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import Decision, RiskLevel
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.blacklist import check_all_blacklists
from app.service.enrichment import enrich_request_context
from app.service.validator import validate_business_entity


logger = logging.getLogger(__name__)


async def process_event(
    db: AsyncSession,
    request: RiskCheckRequest,
    *,
    decision_time: datetime | None = None,
) -> RiskCheckResponse:
    """校验 → 补全 → 黑名单 → 决策；异常时整体回滚。"""

    async with db.begin():
        context = await validate_business_entity(db, request)
        context = await enrich_request_context(db, context)
        blacklist_hit = await check_all_blacklists(db, context)
        if blacklist_hit is not None:
            logger.warning(
                "风险事件命中黑名单",
                extra={
                    "user_id": request.user_id,
                    "source_id": request.source_id,
                    "blacklist_type": blacklist_hit.blacklist_type.value,
                },
            )
            return RiskCheckResponse(
                user_id=request.user_id,
                final_score=100,
                risk_level=RiskLevel.EXTREME,
                decision=Decision.REJECT,
                message=f"撞黑名单: {blacklist_hit.blacklist_type.value}",
                blocked_by=blacklist_hit.blacklist_type.value,
                create_time=decision_time or datetime.now(UTC).replace(tzinfo=None),
            )
        return await run_risk_check(db, context, decision_time=decision_time)
