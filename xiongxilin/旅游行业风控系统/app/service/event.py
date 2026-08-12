"""
旅游行业风控事件处理管道。

沿用参考项目 4 步编排：
1. 业务实体校验
2. 自动补全 order_id 和 event_data
3. 黑名单前置拦截
4. 调用决策引擎 run_risk_check
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    BookingFlight,
    BookingHotel,
    BlacklistExtra,
    OrderInfo,
    PassengerInfo,
    TravelComplaint,
    TravelRefund,
    UserInfo,
    VisaApplication,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    request = await _enrich_request(db, request)

    skip_blacklist = bool((request.event_data or {}).get("_skip_blacklist"))
    if not skip_blacklist:
        blocked = await _check_all_blacklists(db, request)
        if blocked is not None:
            logger.warning("撞黑名单: type=%s, user_id=%s, source_id=%s", blocked, request.user_id, request.source_id)
            return _blacklist_reject(request, blocked)

    return await run_risk_check(db, request)


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    order_id = request.order_id

    if request.event_type in ("旅游下单", "支付", "出行前核验"):
        order_id = order_id or request.source_id
    elif request.event_type == "机票预订":
        order_id = (await db.execute(
            select(BookingFlight.order_id).where(BookingFlight.booking_id == request.source_id)
        )).scalar_one_or_none()
    elif request.event_type == "酒店预订":
        order_id = (await db.execute(
            select(BookingHotel.order_id).where(BookingHotel.booking_id == request.source_id)
        )).scalar_one_or_none()
    elif request.event_type == "签证申请":
        order_id = (await db.execute(
            select(VisaApplication.order_id).where(VisaApplication.visa_id == request.source_id)
        )).scalar_one_or_none()
    elif request.event_type == "售后申请":
        order_id = (await db.execute(
            select(TravelRefund.order_id).where(TravelRefund.refund_id == request.source_id)
        )).scalar_one_or_none()
    elif request.event_type == "投诉":
        order_id = (await db.execute(
            select(TravelComplaint.order_id).where(TravelComplaint.complaint_id == request.source_id)
        )).scalar_one_or_none()

    if order_id:
        request.order_id = order_id
        order = (await db.execute(
            select(OrderInfo).where(OrderInfo.order_id == order_id)
        )).scalar_one_or_none()
        if order:
            event_data = dict(request.event_data or {})
            event_data.update({
                "order_id": order.order_id,
                "order_type": order.order_type,
                "total_amount": float(order.total_amount or 0),
                "dest_country": order.dest_country,
                "dest_city": order.dest_city,
                "depart_date": str(order.depart_date),
                "return_date": str(order.return_date) if order.return_date else None,
                "passenger_count": order.passenger_count,
                "pay_account": order.pay_account,
                "device_id": order.device_id,
                "ip_address": order.ip_address,
            })
            request.event_data = event_data

    return request


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    if await _hit_blacklist(db, "用户", request.user_id):
        return "用户"

    order = None
    if request.order_id:
        order = (await db.execute(
            select(OrderInfo).where(OrderInfo.order_id == request.order_id)
        )).scalar_one_or_none()

    if order:
        for bl_type, value in (
            ("订单", order.order_id),
            ("支付账号", order.pay_account),
            ("设备指纹", order.device_id),
            ("IP", order.ip_address),
        ):
            if value and await _hit_blacklist(db, bl_type, value):
                return bl_type

        passengers = list((await db.execute(
            select(PassengerInfo).where(PassengerInfo.order_id == order.order_id)
        )).scalars().all())
        for passenger in passengers:
            for bl_type, value in (
                ("身份证号", passenger.id_number),
                ("护照号", passenger.passport_no),
            ):
                if value and await _hit_blacklist(db, bl_type, value):
                    return bl_type

    user = (await db.execute(
        select(UserInfo.phone, UserInfo.pay_account, UserInfo.device_id, UserInfo.login_ip)
        .where(UserInfo.user_id == request.user_id)
    )).first()
    if user:
        for bl_type, value in (
            ("手机号", user.phone),
            ("支付账号", user.pay_account),
            ("设备指纹", user.device_id),
            ("IP", user.login_ip),
        ):
            if value and await _hit_blacklist(db, bl_type, value):
                return bl_type

    return None


async def _hit_blacklist(db: AsyncSession, blacklist_type: str, value: str) -> bool:
    if await check_blacklist(db, blacklist_type, value):
        return True

    row = (await db.execute(
        select(BlacklistExtra.entry_id).where(
            BlacklistExtra.type == blacklist_type,
            BlacklistExtra.value == value,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="拒绝",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        blocked_by=blocked_by,
    )
