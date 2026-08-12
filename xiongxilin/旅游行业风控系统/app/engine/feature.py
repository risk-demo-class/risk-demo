"""
旅游行业特征工程模块。

保持参考项目三大特征族：
  user_*  用户维度
  order_* 订单/业务单据维度
  addr_*  目的地/航线/酒店城市维度
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingFlight,
    BookingHotel,
    DestinationRisk,
    OrderInfo,
    PassengerInfo,
    TravelComplaint,
    TravelRefund,
    UserInfo,
    VisaApplication,
)


async def _count(model, db: AsyncSession, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    now = datetime.now()
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)
    since_90d = now - timedelta(days=90)

    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one_or_none()
    account_age_days = float(user.account_age_days if user else 0)
    real_name_passed = 1.0 if user and user.real_name_status == "已实名" else 0.0

    total_orders = await _count(OrderInfo, db, user_id=user_id)

    orders_7d = float((await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.create_time >= since_7d,
        )
    )).scalar() or 0)
    orders_30d = float((await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.create_time >= since_30d,
        )
    )).scalar() or 0)
    total_amount = float((await db.execute(
        select(func.coalesce(func.sum(OrderInfo.total_amount), 0)).where(OrderInfo.user_id == user_id)
    )).scalar() or 0)
    total_amount_30d = float((await db.execute(
        select(func.coalesce(func.sum(OrderInfo.total_amount), 0)).where(
            OrderInfo.user_id == user_id,
            OrderInfo.create_time >= since_30d,
        )
    )).scalar() or 0)

    refund_count_90d = float((await db.execute(
        select(func.count()).select_from(TravelRefund).where(
            TravelRefund.user_id == user_id,
            TravelRefund.apply_time >= since_90d,
        )
    )).scalar() or 0)
    complaint_count_90d = float((await db.execute(
        select(func.count()).select_from(TravelComplaint).where(
            TravelComplaint.user_id == user_id,
            TravelComplaint.complaint_time >= since_90d,
        )
    )).scalar() or 0)
    visa_reject_count_90d = float((await db.execute(
        select(func.count()).select_from(VisaApplication).where(
            VisaApplication.user_id == user_id,
            VisaApplication.submit_time >= since_90d,
            VisaApplication.visa_status == "拒签",
        )
    )).scalar() or 0)
    visa_country_count_30d = float((await db.execute(
        select(func.count(func.distinct(VisaApplication.dest_country))).where(
            VisaApplication.user_id == user_id,
            VisaApplication.submit_time >= since_30d,
        )
    )).scalar() or 0)
    passenger_count_30d = float((await db.execute(
        select(func.count(func.distinct(PassengerInfo.id_number)))
        .select_from(PassengerInfo)
        .join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == user_id, OrderInfo.create_time >= since_30d)
    )).scalar() or 0)

    device_account_count = 0.0
    pay_account_order_count_1h = 0.0
    if user:
        device_account_count = float((await db.execute(
            select(func.count(func.distinct(UserInfo.user_id))).where(UserInfo.device_id == user.device_id)
        )).scalar() or 0)
        pay_account_order_count_1h = float((await db.execute(
            select(func.count()).select_from(OrderInfo).where(
                OrderInfo.pay_account == user.pay_account,
                OrderInfo.create_time >= now - timedelta(hours=1),
            )
        )).scalar() or 0)

    refund_rate_90d = round(refund_count_90d / total_orders, 4) if total_orders else 0.0
    avg_order_amount = round(total_amount / total_orders, 2) if total_orders else 0.0

    return {
        "user_total_orders": total_orders,
        "user_account_age_days": account_age_days,
        "user_real_name_passed": real_name_passed,
        "user_orders_7d": orders_7d,
        "user_orders_30d": orders_30d,
        "user_total_amount": total_amount,
        "user_total_amount_30d": total_amount_30d,
        "user_avg_order_amount": avg_order_amount,
        "user_refund_count_90d": refund_count_90d,
        "user_refund_rate_90d": refund_rate_90d,
        "user_complaint_count_90d": complaint_count_90d,
        "user_visa_reject_count_90d": visa_reject_count_90d,
        "user_visa_country_count_30d": visa_country_count_30d,
        "user_passenger_count_30d": passenger_count_30d,
        "user_device_account_count": device_account_count,
        "user_pay_account_order_count_1h": pay_account_order_count_1h,
    }


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    order = (await db.execute(select(OrderInfo).where(OrderInfo.order_id == order_id))).scalar_one_or_none()
    if not order:
        return {}

    today = date.today()
    days_to_departure = (order.depart_date - today).days if order.depart_date else 0
    trip_days = ((order.return_date or order.depart_date) - order.depart_date).days if order.depart_date else 0
    is_night = 1.0 if order.create_time and 1 <= order.create_time.hour <= 5 else 0.0

    dest = (await db.execute(
        select(DestinationRisk).where(
            DestinationRisk.country == order.dest_country,
            DestinationRisk.city == order.dest_city,
        ).limit(1)
    )).scalar_one_or_none()
    destination_risk_score = float(dest.risk_score if dest else 0)
    is_cross_border = float(dest.is_cross_border if dest else (0 if order.dest_country == "中国" else 1))

    historical_passengers = set((await db.execute(
        select(PassengerInfo.id_number)
        .join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == order.user_id, OrderInfo.order_id != order_id)
    )).scalars().all())
    current_passengers = set((await db.execute(
        select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
    )).scalars().all())
    if not current_passengers:
        passenger_match_rate = 0.0
    elif not historical_passengers:
        passenger_match_rate = 0.0
    else:
        passenger_match_rate = round(len(current_passengers & historical_passengers) / len(current_passengers), 4)

    same_flight_ticket_count_1h = 0.0
    flight = (await db.execute(
        select(BookingFlight).where(BookingFlight.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if flight:
        since = order.create_time - timedelta(hours=1)
        until = order.create_time + timedelta(hours=1)
        same_flight_ticket_count_1h = float((await db.execute(
            select(func.coalesce(func.sum(BookingFlight.ticket_count), 0))
            .select_from(BookingFlight)
            .join(OrderInfo, BookingFlight.order_id == OrderInfo.order_id)
            .where(
                BookingFlight.flight_no == flight.flight_no,
                OrderInfo.pay_account == order.pay_account,
                OrderInfo.create_time.between(since, until),
            )
        )).scalar() or 0)

    high_value_hotel_near_departure = 0.0
    hotel = (await db.execute(
        select(BookingHotel).where(BookingHotel.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if hotel and days_to_departure <= 3 and float(order.total_amount or 0) >= 8000:
        high_value_hotel_near_departure = 1.0

    material_change_count = float((await db.execute(
        select(func.coalesce(func.max(VisaApplication.material_change_count), 0))
        .where(VisaApplication.order_id == order_id)
    )).scalar() or 0)

    refund_amount = float((await db.execute(
        select(func.coalesce(func.sum(TravelRefund.refund_amount), 0))
        .where(TravelRefund.order_id == order_id)
    )).scalar() or 0)
    order_total = float(order.total_amount or 0)
    refund_amount_rate = round(refund_amount / order_total, 4) if order_total else 0.0

    return {
        "order_total_amount": order_total,
        "order_passenger_count": float(order.passenger_count or 0),
        "order_days_to_departure": float(days_to_departure),
        "order_trip_days": float(trip_days),
        "order_is_cross_border": is_cross_border,
        "order_is_night": is_night,
        "order_destination_risk_score": destination_risk_score,
        "order_passenger_match_rate": passenger_match_rate,
        "order_same_flight_ticket_count_1h": same_flight_ticket_count_1h,
        "order_high_value_hotel_near_departure": high_value_hotel_near_departure,
        "order_material_change_count": material_change_count,
        "order_refund_amount_rate": refund_amount_rate,
    }


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
    order_id: str | None = None,
) -> dict[str, float]:
    order = None
    if order_id:
        order = (await db.execute(select(OrderInfo).where(OrderInfo.order_id == order_id))).scalar_one_or_none()

    if not order:
        return {
            "addr_destination_risk_score": 0.0,
            "addr_destination_order_count_7d": 0.0,
            "addr_distinct_country_count_30d": 0.0,
            "addr_is_new_destination": 0.0,
            "addr_hotel_city_order_count_7d": 0.0,
            "addr_route_order_count_1h": 0.0,
        }

    now = datetime.now()
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    destination_risk_score = float((await db.execute(
        select(func.coalesce(func.max(DestinationRisk.risk_score), 0)).where(
            DestinationRisk.country == order.dest_country,
            DestinationRisk.city == order.dest_city,
        )
    )).scalar() or 0)
    destination_order_count_7d = float((await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.dest_country == order.dest_country,
            OrderInfo.dest_city == order.dest_city,
            OrderInfo.create_time >= since_7d,
        )
    )).scalar() or 0)
    distinct_country_count_30d = float((await db.execute(
        select(func.count(func.distinct(OrderInfo.dest_country))).where(
            OrderInfo.user_id == user_id,
            OrderInfo.create_time >= since_30d,
        )
    )).scalar() or 0)
    previous_destination_count = float((await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.dest_country == order.dest_country,
            OrderInfo.dest_city == order.dest_city,
            OrderInfo.order_id != order.order_id,
        )
    )).scalar() or 0)

    hotel_city_order_count_7d = 0.0
    hotel = (await db.execute(
        select(BookingHotel).where(BookingHotel.order_id == order.order_id).limit(1)
    )).scalar_one_or_none()
    if hotel:
        hotel_city_order_count_7d = float((await db.execute(
            select(func.count())
            .select_from(BookingHotel)
            .join(OrderInfo, BookingHotel.order_id == OrderInfo.order_id)
            .where(
                OrderInfo.user_id == user_id,
                BookingHotel.city == hotel.city,
                OrderInfo.create_time >= since_7d,
            )
        )).scalar() or 0)

    route_order_count_1h = 0.0
    flight = (await db.execute(
        select(BookingFlight).where(BookingFlight.order_id == order.order_id).limit(1)
    )).scalar_one_or_none()
    if flight:
        route_order_count_1h = float((await db.execute(
            select(func.count())
            .select_from(BookingFlight)
            .join(OrderInfo, BookingFlight.order_id == OrderInfo.order_id)
            .where(
                BookingFlight.depart_airport == flight.depart_airport,
                BookingFlight.arrive_airport == flight.arrive_airport,
                OrderInfo.create_time.between(order.create_time - timedelta(hours=1), order.create_time + timedelta(hours=1)),
            )
        )).scalar() or 0)

    return {
        "addr_destination_risk_score": destination_risk_score,
        "addr_destination_order_count_7d": destination_order_count_7d,
        "addr_distinct_country_count_30d": distinct_country_count_30d,
        "addr_is_new_destination": 1.0 if previous_destination_count == 0 else 0.0,
        "addr_hotel_city_order_count_7d": hotel_city_order_count_7d,
        "addr_route_order_count_1h": route_order_count_1h,
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id, order_id))
    return features
