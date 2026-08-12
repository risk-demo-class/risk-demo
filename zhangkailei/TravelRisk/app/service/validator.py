"""旅游事件实体存在性与归属校验。"""
import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FlightBooking, HotelBooking, PaymentRecord, TravelOrder, TravelUser, VisaApplication
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)

_EVENT_SOURCE_VALIDATORS = {
    "机票预订": (FlightBooking, "booking_id", "机票预订"),
    "酒店预订": (HotelBooking, "booking_id", "酒店预订"),
    "签证申请": (VisaApplication, "visa_id", "签证申请"),
    "订单支付": (PaymentRecord, "payment_id", "支付记录"),
}


async def ensure_exists(db: AsyncSession, model, field_name: str, value: str, label: str) -> None:
    if not value:
        raise HTTPException(400, detail=f"{label}ID不能为空")
    count = (await db.execute(select(func.count()).select_from(model).where(
        getattr(model, field_name) == value))).scalar() or 0
    if not count:
        raise HTTPException(404, detail=f"{label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, TravelUser, "user_id", user_id, "旅游用户")


async def resolve_source_order_and_owner(
    db: AsyncSession, request: RiskCheckRequest,
) -> tuple[str, str]:
    if request.event_type == "机票预订":
        source = (await db.execute(select(FlightBooking).where(
            FlightBooking.booking_id == request.source_id))).scalar_one_or_none()
        order_id = source.order_id if source else ""
    elif request.event_type == "酒店预订":
        source = (await db.execute(select(HotelBooking).where(
            HotelBooking.booking_id == request.source_id))).scalar_one_or_none()
        order_id = source.order_id if source else ""
    elif request.event_type == "签证申请":
        source = (await db.execute(select(VisaApplication).where(
            VisaApplication.visa_id == request.source_id))).scalar_one_or_none()
        return (source.order_id, source.user_id) if source else ("", "")
    else:
        source = (await db.execute(select(PaymentRecord).where(
            PaymentRecord.payment_id == request.source_id))).scalar_one_or_none()
        return (source.order_id, source.user_id) if source else ("", "")

    owner = (await db.execute(select(TravelOrder.user_id).where(
        TravelOrder.order_id == order_id))).scalar_one_or_none()
    return order_id, owner or ""


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    model, field, label = _EVENT_SOURCE_VALIDATORS[request.event_type]
    await ensure_exists(db, model, field, request.source_id, label)


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    order_id, owner = await resolve_source_order_and_owner(db, request)
    if not order_id:
        raise HTTPException(400, detail="事件无法关联旅游订单")
    if owner != request.user_id:
        logger.warning("旅游事件归属不一致 source=%s owner=%s request_user=%s",
                       request.source_id, owner, request.user_id)
        raise HTTPException(403, detail="事件不属于当前用户")
