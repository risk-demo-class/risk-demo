"""
旅游行业业务实体校验器。

职责和参考项目一致：
1. 校验用户存在
2. 校验 source_id 与 event_type 指向的业务表匹配
3. 校验业务单据归属用户，防止水平越权
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingFlight,
    BookingHotel,
    OrderInfo,
    TravelComplaint,
    TravelRefund,
    UserInfo,
    VisaApplication,
)
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def ensure_exists(
    db: AsyncSession,
    model: type,
    field_name: str,
    value: Any,
    *,
    entity_label: str,
    field_label: Optional[str] = None,
    cast_value: Optional[Callable[[Any], Any]] = None,
    status_code: int = 404,
) -> None:
    field_label = field_label or f"{entity_label}ID"
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    compare_value = cast_value(value) if cast_value else value
    stmt = (
        select(func.count())
        .select_from(model)
        .where(getattr(model, field_name) == compare_value)
        .limit(1)
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    owner = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"订单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订单 {order_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


async def _order_id_from_source(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    if request.event_type in ("旅游下单", "支付", "出行前核验"):
        return request.order_id or request.source_id

    if request.event_type == "机票预订":
        return (await db.execute(
            select(BookingFlight.order_id).where(BookingFlight.booking_id == request.source_id)
        )).scalar_one_or_none()

    if request.event_type == "酒店预订":
        return (await db.execute(
            select(BookingHotel.order_id).where(BookingHotel.booking_id == request.source_id)
        )).scalar_one_or_none()

    if request.event_type == "签证申请":
        return (await db.execute(
            select(VisaApplication.order_id).where(VisaApplication.visa_id == request.source_id)
        )).scalar_one_or_none()

    if request.event_type == "售后申请":
        return (await db.execute(
            select(TravelRefund.order_id).where(TravelRefund.refund_id == request.source_id)
        )).scalar_one_or_none()

    if request.event_type == "投诉":
        return (await db.execute(
            select(TravelComplaint.order_id).where(TravelComplaint.complaint_id == request.source_id)
        )).scalar_one_or_none()

    return None


_EVENT_SOURCE_VALIDATORS = {
    ("旅游下单", "支付", "出行前核验"): (OrderInfo, "order_id", "订单", 400),
    ("机票预订",): (BookingFlight, "booking_id", "机票预订", 400),
    ("酒店预订",): (BookingHotel, "booking_id", "酒店预订", 400),
    ("签证申请",): (VisaApplication, "visa_id", "签证申请", 400),
    ("售后申请",): (TravelRefund, "refund_id", "售后单", 400),
    ("投诉",): (TravelComplaint, "complaint_id", "投诉记录", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    for event_types, (model, field, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label,
            status_code=status_code,
        )
        return

    logger.warning("未配置 source_id 校验规则: event_type=%s source_id=%s", request.event_type, request.source_id)


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)

    order_id = await _order_id_from_source(db, request)
    if order_id:
        await ensure_order_belongs_to_user(db, order_id, request.user_id)
