"""
特征工程模块.

按 config/features.yaml 的特征列表, 从旅游业务表计算风控特征.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.feature_registry import FEATURE_COLUMNS
from app.models import (
    BookingFlight,
    BookingHotel,
    DeviceFingerprint,
    GroupBooking,
    HotelPreauthorization,
    OrderInfo,
    PassengerInfo,
    TicketChangeApplication,
    UserInfo,
    VisaApplication,
)

logger = logging.getLogger(__name__)

HIGH_RISK_COUNTRIES = {
    "叙利亚",
    "伊拉克",
    "阿富汗",
    "索马里",
    "也门",
    "利比亚",
    "乌克兰",
    "苏丹",
    "中非",
}


async def _count(model, db: AsyncSession, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum_col(model, col, db: AsyncSession, **filters) -> float:
    stmt = select(func.coalesce(func.sum(getattr(model, col)), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _max_col(model, col, db: AsyncSession, **filters) -> float:
    stmt = select(func.coalesce(func.max(getattr(model, col)), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _get_order(db: AsyncSession, order_id: str | None) -> Optional[OrderInfo]:
    if not order_id:
        return None
    return (
        await db.execute(select(OrderInfo).where(OrderInfo.order_id == order_id).limit(1))
    ).scalar_one_or_none()


# ============================================================
# 用户维度特征
# ============================================================


async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    return await _count(OrderInfo, db, user_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    return await _sum_col(OrderInfo, "total_amount", db, user_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession,
    user_id: str,
    total_orders: float | None = None,
) -> float:
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders <= 0:
        return 0.0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    return await _max_col(OrderInfo, "total_amount", db, user_id=user_id)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.order_status.like("%取消%"),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    return await _count(TicketChangeApplication, db, user_id=user_id)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    stmt = (
        select(
            func.coalesce(
                func.sum(
                    func.abs(
                        func.coalesce(TicketChangeApplication.new_amount, 0)
                        - func.coalesce(TicketChangeApplication.old_amount, 0)
                    )
                ),
                0,
            )
        )
        .select_from(TicketChangeApplication)
        .where(TicketChangeApplication.user_id == user_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_rate(
    db: AsyncSession,
    user_id: str,
    total_orders: float | None = None,
) -> float:
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders <= 0:
        return 0.0
    refund_count = await _feat_user_refund_count(db, user_id)
    return round(refund_count / total_orders, 4)


async def _feat_user_visa_reject_90d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.count()).select_from(VisaApplication).where(
        VisaApplication.user_id == user_id,
        VisaApplication.reject_history == 1,
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visa_countries_30d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=30)
    stmt = (
        select(func.count(distinct(VisaApplication.dest_country)))
        .select_from(VisaApplication)
        .where(VisaApplication.user_id == user_id, VisaApplication.submit_time >= since)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_passenger_id_count(db: AsyncSession, user_id: str) -> float:
    stmt = (
        select(
            func.count(
                distinct(
                    func.coalesce(
                        PassengerInfo.passport_no,
                        PassengerInfo.id_number,
                    )
                )
            )
        )
        .select_from(PassengerInfo)
        .where(PassengerInfo.user_id == user_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_device_count(db: AsyncSession, user_id: str) -> float:
    stmt = (
        select(func.count(distinct(DeviceFingerprint.device_id)))
        .select_from(DeviceFingerprint)
        .where(DeviceFingerprint.user_id == user_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算用户维度特征."""
    total_orders = await _feat_user_total_orders(db, user_id)
    return {
        "user_total_orders": total_orders,
        "user_orders_30d": await _feat_user_orders_30d(db, user_id),
        "user_orders_7d": await _feat_user_orders_7d(db, user_id),
        "user_total_amount": await _feat_user_total_amount(db, user_id),
        "user_avg_order_amount": await _feat_user_avg_order_amount(
            db, user_id, total_orders=total_orders
        ),
        "user_max_order_amount": await _feat_user_max_order_amount(db, user_id),
        "user_cancel_count": await _feat_user_cancel_count(db, user_id),
        "user_refund_count": await _feat_user_refund_count(db, user_id),
        "user_refund_rate": await _feat_user_refund_rate(
            db, user_id, total_orders=total_orders
        ),
        "user_refund_amount": await _feat_user_refund_amount(db, user_id),
        "user_visa_reject_90d": await _feat_user_visa_reject_90d(db, user_id),
        "user_visa_countries_30d": await _feat_user_visa_countries_30d(db, user_id),
        "user_passenger_id_count": await _feat_user_passenger_id_count(db, user_id),
        "user_device_count": await _feat_user_device_count(db, user_id),
    }


# ============================================================
# 订单维度特征
# ============================================================


async def _feat_order_hotel_room_count(db: AsyncSession, order_id: str) -> float:
    return await _sum_col(BookingHotel, "room_count", db, order_id=order_id)


async def _feat_order_flight_count(db: AsyncSession, order_id: str) -> float:
    return await _count(BookingFlight, db, order_id=order_id)


async def _feat_order_preauth_diff(db: AsyncSession, order_id: str) -> float:
    stmt = (
        select(
            func.coalesce(
                func.max(
                    func.abs(
                        func.coalesce(HotelPreauthorization.preauth_amount, 0)
                        - func.coalesce(HotelPreauthorization.actual_amount, 0)
                    )
                ),
                0,
            )
        )
        .select_from(HotelPreauthorization)
        .where(HotelPreauthorization.order_id == order_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_group_member_count(db: AsyncSession, order_id: str) -> float:
    stmt = (
        select(func.coalesce(func.max(GroupBooking.member_count), 0))
        .select_from(GroupBooking)
        .where(GroupBooking.order_id == order_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


def _dest_risk_score(dest_country: Optional[str]) -> float:
    if not dest_country:
        return 0.0
    if dest_country in HIGH_RISK_COUNTRIES:
        return 80.0
    if dest_country in {"美国", "英国", "澳大利亚", "日本"}:
        return 20.0
    return 0.0


async def compute_order_features(
    db: AsyncSession,
    order_id: str | None,
) -> dict[str, float]:
    """计算订单维度特征."""
    empty = {
        "order_total_amount": 0.0,
        "order_passenger_count": 0.0,
        "order_hotel_room_count": 0.0,
        "order_flight_count": 0.0,
        "order_trip_days": 0.0,
        "order_days_to_departure": 0.0,
        "order_is_night": 0.0,
        "order_dest_risk_score": 0.0,
        "order_preauth_diff": 0.0,
        "order_group_member_count": 0.0,
    }
    order = await _get_order(db, order_id)
    if not order:
        return empty

    trip_days = 0.0
    if order.depart_date and order.return_date:
        trip_days = float(max((order.return_date - order.depart_date).days, 0))

    days_to_departure = 0.0
    if order.depart_date:
        days_to_departure = float((order.depart_date - date.today()).days)

    is_night = 1.0 if order.create_time and order.create_time.hour in range(1, 6) else 0.0
    passenger_count = float(order.passenger_count or 0)
    if passenger_count <= 0:
        passenger_count = await _count(PassengerInfo, db, order_id=order_id)

    return {
        "order_total_amount": float(order.total_amount or 0),
        "order_passenger_count": passenger_count,
        "order_hotel_room_count": await _feat_order_hotel_room_count(db, order_id),
        "order_flight_count": await _feat_order_flight_count(db, order_id),
        "order_trip_days": trip_days,
        "order_days_to_departure": days_to_departure,
        "order_is_night": is_night,
        "order_dest_risk_score": _dest_risk_score(order.dest_country),
        "order_preauth_diff": await _feat_order_preauth_diff(db, order_id),
        "order_group_member_count": await _feat_order_group_member_count(db, order_id),
    }


# ============================================================
# 设备 / 行为时序 / 乘客特征
# ============================================================


async def _feat_device_user_count_7d(db: AsyncSession, order: Optional[OrderInfo]) -> float:
    if not order or not order.device_id:
        return 0.0
    since = datetime.now() - timedelta(days=7)
    stmt = (
        select(func.count(distinct(OrderInfo.user_id)))
        .select_from(OrderInfo)
        .where(
            OrderInfo.device_id == order.device_id,
            OrderInfo.create_time >= since,
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_device_hotel_account_count(db: AsyncSession, order: Optional[OrderInfo]) -> float:
    if not order or not order.device_id:
        return 0.0
    since = datetime.now() - timedelta(days=7)
    stmt = (
        select(func.count(distinct(OrderInfo.user_id)))
        .select_from(OrderInfo)
        .where(
            OrderInfo.device_id == order.device_id,
            OrderInfo.order_type == "酒店",
            OrderInfo.create_time >= since,
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_same_pay_account_1h_orders(db: AsyncSession, order: Optional[OrderInfo]) -> float:
    if not order or not order.pay_account:
        return 0.0
    start = order.create_time - timedelta(hours=1)
    end = order.create_time + timedelta(hours=1)
    stmt = (
        select(func.count())
        .select_from(OrderInfo)
        .where(
            OrderInfo.pay_account == order.pay_account,
            OrderInfo.create_time >= start,
            OrderInfo.create_time <= end,
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_same_flight_1h_bookings(db: AsyncSession, order: Optional[OrderInfo]) -> float:
    if not order or not order.create_time:
        return 0.0
    start = order.create_time - timedelta(hours=1)
    end = order.create_time + timedelta(hours=1)
    stmt = (
        select(func.count(distinct(BookingFlight.booking_id)))
        .select_from(BookingFlight)
        .join(OrderInfo, BookingFlight.order_id == OrderInfo.order_id)
        .where(
            BookingFlight.flight_no.in_(
                select(BookingFlight.flight_no).where(BookingFlight.order_id == order.order_id)
            ),
            OrderInfo.create_time >= start,
            OrderInfo.create_time <= end,
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_consecutive_refund_change(db: AsyncSession, user_id: str) -> float:
    stmt = (
        select(TicketChangeApplication.apply_time)
        .where(TicketChangeApplication.user_id == user_id)
        .order_by(TicketChangeApplication.apply_time.desc())
    )
    flattened = [t for t in (await db.execute(stmt)).scalars().all() if t is not None]
    if not flattened:
        return 0.0
    streak = 1
    for i in range(1, len(flattened)):
        gap = (flattened[i - 1] - flattened[i]).days
        if gap <= 3:
            streak += 1
        else:
            break
    return float(streak)


async def _feat_passenger_match_rate(
    db: AsyncSession,
    user_id: str,
    order_id: str | None,
) -> float:
    if not order_id:
        return 0.0
    current = list(
        (
            await db.execute(
                select(PassengerInfo).where(PassengerInfo.order_id == order_id)
            )
        ).scalars().all()
    )
    if not current:
        return 0.0
    history_stmt = (
        select(distinct(func.coalesce(PassengerInfo.passport_no, PassengerInfo.id_number)))
        .select_from(PassengerInfo)
        .where(PassengerInfo.user_id == user_id)
    )
    history_ids = {str(v) for v in (await db.execute(history_stmt)).scalars().all() if v}
    current_ids = [
        str(p.passport_no or p.id_number or "")
        for p in current
        if p.passport_no or p.id_number
    ]
    if not current_ids:
        return 0.0
    matched = sum(1 for cid in current_ids if cid in history_ids)
    return round(matched / len(current_ids), 4)


async def compute_behavior_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None,
) -> dict[str, float]:
    """计算设备 / 行为时序 / 乘客特征."""
    order = await _get_order(db, order_id)
    return {
        "device_user_count_7d": await _feat_device_user_count_7d(db, order),
        "device_hotel_account_count": await _feat_device_hotel_account_count(db, order),
        "same_pay_account_1h_orders": await _feat_same_pay_account_1h_orders(db, order),
        "same_flight_1h_bookings": await _feat_same_flight_1h_bookings(db, order),
        "user_consecutive_refund_change": await _feat_user_consecutive_refund_change(db, user_id),
        "passenger_match_rate": await _feat_passenger_match_rate(db, user_id, order_id),
    }


# ============================================================
# LLM 语义特征
# ============================================================


async def compute_llm_features(
    db: AsyncSession,
    order_id: str | None,
    event_data: Optional[dict],
) -> dict[str, float]:
    """根据订单备注调用 DeepSeek, 失败时兜底 0."""
    default = {
        "remark_llm_score": 0.0,
        "remark_scalper_flag": 0.0,
        "remark_illegal_group_buy_flag": 0.0,
    }
    remark = (event_data or {}).get("order_remark")
    if not remark:
        return default
    try:
        from app.llm.remark_analyzer import analyze_order_remark

        result = await analyze_order_remark(remark)
        return {
            "remark_llm_score": float(result.get("score", 0)),
            "remark_scalper_flag": 1.0 if result.get("risk_type") == "scalper_code" else 0.0,
            "remark_illegal_group_buy_flag": (
                1.0 if result.get("risk_type") == "illegal_group_buy" else 0.0
            ),
        }
    except Exception:
        logger.exception("LLM 特征计算失败, 使用兜底 0: order_id=%s", order_id)
        return default


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    event_data: Optional[dict] = None,
) -> dict[str, float]:
    """计算全部启用特征并合并."""
    try:
        features: dict[str, float] = {}
        features.update(await compute_user_features(db, user_id))
        features.update(await compute_order_features(db, order_id))
        features.update(await compute_behavior_features(db, user_id, order_id))
        features.update(await compute_llm_features(db, order_id, event_data))

        return {name: float(features.get(name, 0.0)) for name in FEATURE_COLUMNS}
    except Exception:
        logger.exception("特征计算失败: user_id=%s order_id=%s", user_id, order_id)
        raise
