from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models_business import UserDevice
from app.models_risk import RiskBlacklist
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.validator import validate_risk_check_request


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. Validate business entity and ownership.
    await validate_risk_check_request(db, request)

    # 2. Enrich generic order/device slots.
    if request.event_type == "支付" and request.order_id is None:
        request = request.model_copy(update={"order_id": request.source_id})
    if request.receive_id is None:
        device_id = (
            await db.execute(select(UserDevice.device_id).where(UserDevice.user_id == request.user_id).limit(1))
        ).scalar_one_or_none()
        if device_id:
            request = request.model_copy(update={"receive_id": device_id})

    # 3. Pre-decision blacklist check.
    blocked = (
        await db.execute(
            select(RiskBlacklist.blacklist_id).where(
                RiskBlacklist.blacklist_type == "用户",
                RiskBlacklist.blacklist_value == f"USER:{request.user_id}",
                RiskBlacklist.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if blocked is not None:
        raise PermissionError("subject is blacklisted")

    # 4. Enter the fixed seven-step risk decision pipeline.
    return await run_risk_check(db, request)

