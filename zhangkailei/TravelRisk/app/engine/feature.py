"""旅游行业 25 维特征计算。所有金额使用数据库聚合，返回 float 字典。"""
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    FlightBooking, HotelBooking, OrderPassenger, PassengerInfo, PaymentRecord,
    TravelBlacklistEntry, TravelOrder, TravelUser, VisaApplication,
)


async def _scalar(db: AsyncSession, stmt, default=0):
    return (await db.execute(stmt)).scalar() or default


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    now = datetime.now()
    d7, d30, d90 = now - timedelta(days=7), now - timedelta(days=30), now - timedelta(days=90)
    user = (await db.execute(select(TravelUser).where(TravelUser.user_id == user_id))).scalar_one()

    order_count_30d = await _scalar(db, select(func.count()).select_from(TravelOrder).where(
        TravelOrder.user_id == user_id, TravelOrder.create_time >= d30))
    country_count = await _scalar(db, select(func.count(distinct(TravelOrder.dest_country))).where(
        TravelOrder.user_id == user_id, TravelOrder.create_time >= d30))
    visa_count = await _scalar(db, select(func.count()).select_from(VisaApplication).where(
        VisaApplication.user_id == user_id, VisaApplication.submit_time >= d30))
    visa_rejects = await _scalar(db, select(func.count()).select_from(VisaApplication).where(
        VisaApplication.user_id == user_id, VisaApplication.submit_time >= d90,
        VisaApplication.application_status == "拒签"))
    total_90d = await _scalar(db, select(func.count()).select_from(TravelOrder).where(
        TravelOrder.user_id == user_id, TravelOrder.create_time >= d90))
    cancel_90d = await _scalar(db, select(func.count()).select_from(TravelOrder).where(
        TravelOrder.user_id == user_id, TravelOrder.create_time >= d90,
        TravelOrder.order_status == "已取消"))
    total_amount = await _scalar(db, select(func.coalesce(func.sum(TravelOrder.total_amount), 0)).where(
        TravelOrder.user_id == user_id, TravelOrder.create_time >= d30))
    device_count = await _scalar(db, select(func.count(distinct(PaymentRecord.device_id))).where(
        PaymentRecord.user_id == user_id, PaymentRecord.payment_time >= d7))

    historical_ids = set((await db.execute(
        select(PassengerInfo.id_number_hash).where(PassengerInfo.user_id == user_id)
    )).scalars().all())
    # 没有具体订单上下文时，匹配率按历史稳定性兜底：有常用乘客为 1，否则 0。
    passenger_match = 1.0 if historical_ids else 0.0

    return {
        "user_account_age_days": float(max((now - user.register_time).days, 0)),
        "user_real_name_status": float(user.real_name_status),
        "user_order_count_30d": float(order_count_30d),
        "user_country_count_30d": float(country_count),
        "user_visa_apply_count_30d": float(visa_count),
        "user_visa_reject_count_90d": float(visa_rejects),
        "user_cancel_rate_90d": round(cancel_90d / total_90d, 4) if total_90d else 0.0,
        "user_total_amount_30d": float(total_amount),
        "user_device_count_7d": float(device_count),
        "user_passenger_match_rate": passenger_match,
    }


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    now = datetime.now()
    order = (await db.execute(select(TravelOrder).where(TravelOrder.order_id == order_id))).scalar_one()
    passengers = int(await _scalar(db, select(func.count()).select_from(OrderPassenger).where(
        OrderPassenger.order_id == order_id)))
    payment = (await db.execute(select(PaymentRecord).where(PaymentRecord.order_id == order_id)
                                .order_by(PaymentRecord.payment_time.desc()).limit(1))).scalar_one_or_none()
    flight = (await db.execute(select(FlightBooking).where(FlightBooking.order_id == order_id))).scalar_one_or_none()
    hotel = (await db.execute(select(HotelBooking).where(HotelBooking.order_id == order_id))).scalar_one_or_none()

    same_flight = 0
    mismatch = 0
    if payment:
        mismatch = int(await _scalar(db, select(func.count(distinct(PaymentRecord.user_id))).where(
            PaymentRecord.payment_account_hash == payment.payment_account_hash)) > 1)
        if flight:
            since = payment.payment_time - timedelta(hours=1)
            same_flight = await _scalar(db, select(func.coalesce(func.sum(FlightBooking.ticket_count), 0))
                .select_from(PaymentRecord).join(TravelOrder, PaymentRecord.order_id == TravelOrder.order_id)
                .join(FlightBooking, TravelOrder.order_id == FlightBooking.order_id).where(
                    PaymentRecord.payment_account_hash == payment.payment_account_hash,
                    PaymentRecord.payment_time >= since,
                    FlightBooking.flight_no == flight.flight_no))

    non_refundable = 0.0
    if hotel and not hotel.is_refundable:
        non_refundable = 1.0
    destination_risk = 100.0 if order.dest_country in settings.TRAVEL_HIGH_RISK_COUNTRIES else 10.0
    return {
        "order_total_amount": float(order.total_amount),
        "order_passenger_count": float(passengers or order.passenger_count),
        "order_days_to_depart": float((order.depart_date - now.date()).days),
        "order_trip_days": float(max((order.return_date - order.depart_date).days, 0)),
        "order_is_cross_border": float(order.dest_country != "中国"),
        "order_is_night": float(0 <= order.create_time.hour < 6),
        "order_same_flight_count_1h": float(same_flight),
        "order_payment_user_mismatch": float(mismatch),
        "order_non_refundable_ratio": non_refundable,
        "order_destination_risk_score": destination_risk,
    }


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None = None,
) -> dict[str, float]:
    """第三特征族沿用 addr_ 前缀，实际表示证件、设备和 IP。"""
    now = datetime.now()
    identities = list((await db.execute(
        select(PassengerInfo.id_number_hash).where(PassengerInfo.user_id == user_id)
    )).scalars().all())
    blacklisted = 0
    duplicate_users = 0
    if identities:
        blacklisted = int(bool((await db.execute(select(TravelBlacklistEntry.entry_id).where(
            TravelBlacklistEntry.entry_type == "PASSPORT",
            TravelBlacklistEntry.entry_value_hash.in_(identities),
            TravelBlacklistEntry.deleted_at.is_(None),
            (TravelBlacklistEntry.expire_time.is_(None) | (TravelBlacklistEntry.expire_time > now)),
        ).limit(1))).scalar_one_or_none()))
        duplicate_users = int(await _scalar(db, select(func.count(distinct(PassengerInfo.user_id))).where(
            PassengerInfo.id_number_hash.in_(identities))))

    payment = (await db.execute(select(PaymentRecord).where(PaymentRecord.user_id == user_id)
                                .order_by(PaymentRecord.payment_time.desc()).limit(1))).scalar_one_or_none()
    device_users, ip_orders = 0, 0
    if payment:
        device_users = await _scalar(db, select(func.count(distinct(PaymentRecord.user_id))).where(
            PaymentRecord.device_id == payment.device_id,
            PaymentRecord.payment_time >= now - timedelta(days=7)))
        ip_orders = await _scalar(db, select(func.count()).select_from(PaymentRecord).where(
            PaymentRecord.ip == payment.ip,
            PaymentRecord.payment_time >= now - timedelta(hours=1)))

    return {
        "addr_passport_blacklisted": float(blacklisted),
        "addr_duplicate_identity_users": float(duplicate_users),
        "addr_nationality_mismatch": 0.0,
        "addr_device_shared_users_7d": float(device_users),
        "addr_ip_booking_count_1h": float(ip_orders),
    }


async def compute_all_features(
    db: AsyncSession, user_id: str, order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
        current_hashes = set((await db.execute(
            select(PassengerInfo.id_number_hash)
            .join(OrderPassenger, PassengerInfo.passenger_id == OrderPassenger.passenger_id)
            .where(OrderPassenger.order_id == order_id)
        )).scalars().all())
        historical_hashes = set((await db.execute(
            select(PassengerInfo.id_number_hash)
            .join(OrderPassenger, PassengerInfo.passenger_id == OrderPassenger.passenger_id)
            .join(TravelOrder, TravelOrder.order_id == OrderPassenger.order_id)
            .where(TravelOrder.user_id == user_id, TravelOrder.order_id != order_id)
        )).scalars().all())
        features["user_passenger_match_rate"] = (
            round(len(current_hashes & historical_hashes) / len(current_hashes), 4)
            if current_hashes else 0.0
        )
    else:
        # 模型输入保持固定 25 维。
        features.update({k: 0.0 for k in (
            "order_total_amount", "order_passenger_count", "order_days_to_depart",
            "order_trip_days", "order_is_cross_border", "order_is_night",
            "order_same_flight_count_1h", "order_payment_user_mismatch",
            "order_non_refundable_ratio", "order_destination_risk_score")})
    features.update(await compute_address_features(db, user_id, receive_id))
    return features
