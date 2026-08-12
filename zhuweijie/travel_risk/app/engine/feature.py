"""
旅游风控系统 - 特征工程模块
通过 ORM 查询旅游业务数据, 实时计算三大特征族: 用户 / 订单 / 目的地.

特征命名前缀 → risk_feature.entity_type 分类 (决策引擎约定):
  user_*   = 用户维度
  order_*  = 订单维度
  其他     = 目的地维度 (兼容基线的 entity_type='地址')
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    RiskBlacklist,
    UserInfo,
    VisaApplication,
)

# 教学用"高风险目的地"集合 (真实场景应接制裁名单/使领馆预警)
HIGH_RISK_COUNTRIES = {"美国", "阿联酋", "缅甸", "柬埔寨"}
# 简化节假日窗口: 1-2月(春运) / 7-8月(暑运) / 10月(国庆)
HOLIDAY_MONTHS = {1, 2, 7, 8, 10}


# ============================================================
# 通用 SQL 工具
# ============================================================

async def _count(db: AsyncSession, model, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(db: AsyncSession, model, col_name: str, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for k, v in filters.items():
        stmt = stmt.where(getattr(model, k) == v)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征
# ============================================================

async def _feat_account_age_days(db: AsyncSession, user_id: str) -> float:
    """注册天数 (新号大单风险信号)"""
    val = (await db.execute(
        select(UserInfo.account_age_days).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    return float(val or 0)


async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    return await _count(db, OrderInfo, user_id=user_id)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id, OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id, OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    return await _sum(db, OrderInfo, "total_amount", user_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    return round(await _feat_user_total_amount(db, user_id) / total_orders, 2)


async def _feat_user_visa_reject_count(db: AsyncSession, user_id: str) -> float:
    """历史拒签次数累计 (拒签套利核心信号)"""
    stmt = select(func.coalesce(func.sum(VisaApplication.reject_history), 0)).select_from(
        VisaApplication
    ).where(VisaApplication.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_country_count(db: AsyncSession, user_id: str) -> float:
    """申请/出行过多少个不同国家 (短期多国签证信号)"""
    countries: set[str] = set()
    rows = (await db.execute(
        select(OrderInfo.dest_country).where(
            OrderInfo.user_id == user_id, OrderInfo.dest_country.isnot(None),
        )
    )).scalars().all()
    countries.update(rows)
    rows = (await db.execute(
        select(VisaApplication.dest_country).where(VisaApplication.user_id == user_id)
    )).scalars().all()
    countries.update(rows)
    return float(len(countries))


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """已取消订单数 (近似退改签滥用信号)"""
    return await _count(db, OrderInfo, user_id=user_id, pay_status="已取消")


async def _feat_user_passport_count(db: AsyncSession, user_id: str) -> float:
    """历史累计乘客人数 (同一人大量购票信号)"""
    stmt = select(func.count()).select_from(PassengerInfo).join(
        OrderInfo, PassengerInfo.order_id == OrderInfo.order_id,
    ).where(OrderInfo.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_blacklist_hit(
    db: AsyncSession, user_id: str, order_id: str | None = None,
) -> float:
    """用户或本单乘客证件是否命中黑名单"""
    if await _count(db, RiskBlacklist, blacklist_type="用户", blacklist_value=user_id):
        return 1.0
    if order_id:
        id_numbers = (await db.execute(
            select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
        )).scalars().all()
        for num in id_numbers:
            if await _count(db, BlacklistExtra, type="护照号", value=num):
                return 1.0
    return 0.0


# ============================================================
# 订单维度特征
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    return await _sum(db, OrderInfo, "total_amount", order_id=order_id)


async def _feat_order_passenger_count(db: AsyncSession, order_id: str) -> float:
    return await _count(db, PassengerInfo, order_id=order_id)


async def _feat_order_days_to_depart(db: AsyncSession, order_id: str) -> float:
    """提前购票天数 = 出发日 - 下单日, 越短越可疑"""
    row = (await db.execute(
        select(OrderInfo.depart_date, OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not row or not row.depart_date:
        return 0.0
    depart = row.depart_date if isinstance(row.depart_date, date) else row.depart_date.date()
    create = row.create_time.date() if row.create_time else datetime.now().date()
    return float(max((depart - create).days, 0))


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """0-5 点下单 = 1"""
    val = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    if not val:
        return 0.0
    return 1.0 if val.hour <= 5 else 0.0


async def _feat_order_is_holiday(db: AsyncSession, order_id: str) -> float:
    """出发日期落在节假日窗口 = 1"""
    val = (await db.execute(
        select(OrderInfo.depart_date).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    if not val:
        return 0.0
    return 1.0 if val.month in HOLIDAY_MONTHS else 0.0


async def _feat_order_cabin_class(db: AsyncSession, order_id: str) -> float:
    """本单最高舱位等级: 经济=0, 公务=1, 头等=2"""
    val = (await db.execute(
        select(func.max(BookingFlight.cabin_class)).select_from(BookingFlight).where(
            BookingFlight.order_id == order_id,
        )
    )).scalar_one_or_none()
    return {"公务舱": 1.0, "头等舱": 2.0}.get(val, 0.0)


async def _feat_order_is_cross_border(db: AsyncSession, order_id: str) -> float:
    val = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    return 1.0 if val and val != "中国" else 0.0


async def _feat_same_flight_booking_count(db: AsyncSession, order_id: str) -> float:
    """同一航班号同一天的总预订数 (黄牛囤票核心信号)"""
    row = (await db.execute(
        select(BookingFlight.flight_no, BookingFlight.depart_time).where(
            BookingFlight.order_id == order_id,
        )
    )).first()
    if not row or not row.flight_no:
        return 1.0
    stmt = (
        select(func.count())
        .select_from(BookingFlight)
        .where(BookingFlight.flight_no == row.flight_no, func.date(BookingFlight.depart_time) == row.depart_time.date())
    )
    return float((await db.execute(stmt)).scalar() or 1)


async def _feat_order_hotel_rooms(db: AsyncSession, order_id: str) -> float:
    return await _sum(db, BookingHotel, "room_count", order_id=order_id)


# ============================================================
# 目的地维度特征 (兼容基线 compute_address_features 签名)
# ============================================================

async def _feat_dest_is_high_risk(db: AsyncSession, order_id: str) -> float:
    val = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    return 1.0 if val and val in HIGH_RISK_COUNTRIES else 0.0


async def _feat_passenger_nationality_match(db: AsyncSession, order_id: str) -> float:
    """乘客国籍与目的地是否匹配 (信息不一致信号)"""
    dest = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    if not dest:
        return 0.0
    nations = (await db.execute(
        select(PassengerInfo.nationality).where(
            PassengerInfo.order_id == order_id, PassengerInfo.nationality.isnot(None),
        )
    )).scalars().all()
    return 1.0 if nations and dest in nations else 0.0


# ============================================================
# 三大特征族入口 (对外 API 与基线一致)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str, order_id: str | None = None) -> dict:
    total_orders = await _feat_user_total_orders(db, user_id)
    return {
        "account_age_days": await _feat_account_age_days(db, user_id),
        "user_total_orders": total_orders,
        "user_orders_7d": await _feat_user_orders_7d(db, user_id),
        "user_orders_30d": await _feat_user_orders_30d(db, user_id),
        "user_total_amount": await _feat_user_total_amount(db, user_id),
        "user_avg_order_amount": await _feat_user_avg_order_amount(db, user_id, total_orders=total_orders),
        "user_visa_reject_count": await _feat_user_visa_reject_count(db, user_id),
        "user_country_count": await _feat_user_country_count(db, user_id),
        "user_cancel_count": await _feat_user_cancel_count(db, user_id),
        "user_passport_count": await _feat_user_passport_count(db, user_id),
        "user_blacklist_hit": await _feat_user_blacklist_hit(db, user_id, order_id=order_id),
    }


async def compute_order_features(db: AsyncSession, order_id: str) -> dict:
    return {
        "order_total_amount": await _feat_order_total_amount(db, order_id),
        "order_passenger_count": await _feat_order_passenger_count(db, order_id),
        "order_days_to_depart": await _feat_order_days_to_depart(db, order_id),
        "order_is_night": await _feat_order_is_night(db, order_id),
        "order_is_holiday": await _feat_order_is_holiday(db, order_id),
        "order_cabin_class": await _feat_order_cabin_class(db, order_id),
        "order_is_cross_border": await _feat_order_is_cross_border(db, order_id),
        "same_flight_booking_count": await _feat_same_flight_booking_count(db, order_id),
        "order_hotel_rooms": await _feat_order_hotel_rooms(db, order_id),
    }


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None = None,
) -> dict:
    """目的地族特征. receive_id 参数名兼容基线, 实际按订单(order_id)计算."""
    if receive_id:
        return {
            "dest_is_high_risk": await _feat_dest_is_high_risk(db, receive_id),
            "passenger_nationality_match": await _feat_passenger_nationality_match(db, receive_id),
        }
    return {"dest_is_high_risk": 0.0, "passenger_nationality_match": 0.0}


async def compute_all_features(
    db: AsyncSession, user_id: str, order_id: str | None = None, receive_id: str | None = None,
) -> dict:
    features = await compute_user_features(db, user_id, order_id=order_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
        features.update({
            "dest_is_high_risk": await _feat_dest_is_high_risk(db, order_id),
            "passenger_nationality_match": await _feat_passenger_nationality_match(db, order_id),
        })
    return features


if __name__ == "__main__":
    print("旅游风控特征工程 — 三大特征族特征名:")
    print("  用户族: account_age_days, user_total_orders, user_orders_7d/30d, "
          "user_total_amount, user_avg_order_amount, user_visa_reject_count, "
          "user_country_count, user_cancel_count, user_passport_count, user_blacklist_hit")
    print("  订单族: order_total_amount, order_passenger_count, order_days_to_depart, "
          "order_is_night, order_is_holiday, order_cabin_class, order_is_cross_border, "
          "same_flight_booking_count, order_hotel_rooms")
    print("  目的地族: dest_is_high_risk, passenger_nationality_match")