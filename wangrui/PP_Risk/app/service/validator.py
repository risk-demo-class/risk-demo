from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import PaymentTransaction, UserInfo
from app.schemas import RiskCheckRequest


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    user = (
        await db.execute(select(UserInfo.user_id).where(UserInfo.user_id == request.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise ValueError(f"user does not exist: {request.user_id}")
    if request.event_type == "支付":
        transaction = (
            await db.execute(
                select(PaymentTransaction.transaction_id).where(
                    PaymentTransaction.transaction_id == request.source_id
                )
            )
        ).scalar_one_or_none()
        if transaction is None:
            raise ValueError(f"transaction does not exist: {request.source_id}")

