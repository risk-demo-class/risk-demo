"""
特征工程模块: 通过 ORM 查询旅游业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户维度特征
  order_xxx  = 订单维度特征
  trip_xxx   = 行程/乘客维度特征 (按 Q5 决策, 沿用 decision.py 默认归类到"地址"实体,
               纯审计标签, 不影响规则引用与决策)

25 维特征与 XGBoost FEATURE_COLUMNS 一一对应, 与 R001-R034 全部规则条件对齐:
  R001 user_visa_reject_90d | R002 user_visa_countries_30d | R005 order_total_amount
  R008 trip_same_flight_1h  | R012 order_is_night+order_trip_days | R018 trip_passenger_match_rate
  R025 user_account_age_days+order_total_amount | R030 trip_blacklist_passport_count
  R031 user_refund_rate     | R032 order_passenger_count+trip_distinct_passenger_count
  R033 order_is_urgent+order_is_flight | R034 trip_same_hotel_1h
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingFlight,
    BookingHotel,
    OrderInfo,
    OrderRefund,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)
from app.models_risk import RiskBlacklist


# 通用 SQL 工具
async def _count(model, db: AsyncSession, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, db: AsyncSession, col_name: str, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (11 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史订单总数"""
    return await _count(OrderInfo, db, user_id=user_id)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天订单数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天订单数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史总消费金额"""
    return await _sum(OrderInfo, db, "total_amount", user_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均订单金额 = 总金额 / 订单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    return round(await _feat_user_total_amount(db, user_id) / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔订单金额"""
    stmt = select(func.coalesce(func.max(OrderInfo.total_amount), 0)).where(
        OrderInfo.user_id == user_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visa_reject_90d(db: AsyncSession, user_id: str) -> float:
    """90 天内拒签申请次数 (reject_history>=1 的签证申请) — R001"""
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.count()).select_from(VisaApplication).where(
        VisaApplication.user_id == user_id,
        VisaApplication.reject_history >= 1,
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visa_countries_30d(db: AsyncSession, user_id: str) -> float:
    """30 天内申请签证的不同国家数 — R002"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count(func.distinct(VisaApplication.dest_country))).where(
        VisaApplication.user_id == user_id,
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """账号年龄(天) — R025"""
    row = (await db.execute(
        select(UserInfo.account_age_days).where(UserInfo.user_id == user_id)
    )).first()
    return float(row.account_age_days) if row and row.account_age_days is not None else 0.0


async def _feat_user_real_name_status(db: AsyncSession, user_id: str) -> float:
    """是否实名 1/0"""
    row = (await db.execute(
        select(UserInfo.real_name_status).where(UserInfo.user_id == user_id)
    )).first()
    return float(row.real_name_status) if row and row.real_name_status is not None else 0.0


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """退改率 = 退改单数 / 订单数 — R031"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    refund_count = await _count(OrderRefund, db, user_id=user_id)
    return round(refund_count / total_orders, 4)


# ============================================================
# 订单维度特征 (8 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """订单金额 — R005/R025"""
    row = (await db.execute(
        select(OrderInfo.total_amount).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.total_amount) if row and row.total_amount is not None else 0.0


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否凌晨 1-5 点下单 — R012"""
    row = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 1 <= row.create_time.hour <= 5 else 0.0
    return 0.0


async def _feat_order_trip_days(db: AsyncSession, order_id: str) -> float:
    """行程天数 = 返程-出发 — R012"""
    row = (await db.execute(
        select(OrderInfo.depart_date, OrderInfo.return_date).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.depart_date and row.return_date:
        return max(float((row.return_date - row.depart_date).days), 0)
    return 0.0


async def _feat_order_passenger_count(db: AsyncSession, order_id: str) -> float:
    """订单乘客数 — R032"""
    row = (await db.execute(
        select(OrderInfo.passenger_count).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.passenger_count) if row and row.passenger_count is not None else 0.0


async def _feat_order_is_overseas(db: AsyncSession, order_id: str) -> float:
    """是否跨境 (目的地 != 中国)"""
    row = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.dest_country:
        return 0.0 if row.dest_country == "中国" else 1.0
    return 0.0


async def _feat_order_is_flight(db: AsyncSession, order_id: str) -> float:
    """是否机票订单 — R033"""
    row = (await db.execute(
        select(OrderInfo.order_type).where(OrderInfo.order_id == order_id)
    )).first()
    return 1.0 if row and row.order_type == "机票" else 0.0


async def _feat_order_booking_count(db: AsyncSession, order_id: str) -> float:
    """订单关联的航班+酒店预订数"""
    flight = await _count(BookingFlight, db, order_id=order_id)
    hotel = await _count(BookingHotel, db, order_id=order_id)
    return flight + hotel


async def _feat_order_is_urgent(db: AsyncSession, order_id: str) -> float:
    """是否临近出行 (出发日期 < 7 天) — R033"""
    row = (await db.execute(
        select(OrderInfo.depart_date).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.depart_date:
        return 1.0 if 0 <= (row.depart_date - datetime.now()).days < 7 else 0.0
    return 0.0


# ============================================================
# 行程/乘客维度特征 (6 个)
# ============================================================

async def _get_user_by_order(db: AsyncSession, order_id: str) -> str | None:
    """订单 → 用户ID (行程特征都需要跨订单统计用户)"""
    row = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id)
    )).first()
    return row.user_id if row else None


async def _feat_trip_passenger_match_rate(db: AsyncSession, order_id: str) -> float:
    """乘客证件与用户历史乘客的匹配率 — R018.
    无历史订单时返回 1.0 (无证据不告警); 有历史时 = 本单证件在历史中出现的比例."""
    user_id = await _get_user_by_order(db, order_id)
    if not user_id:
        return 0.0
    cur_ids = list((await db.execute(
        select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
    )).scalars().all())
    if not cur_ids:
        return 0.0
    hist_ids = set((await db.execute(
        select(PassengerInfo.id_number)
        .join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == user_id, OrderInfo.order_id != order_id)
    )).scalars().all())
    if not hist_ids:
        return 1.0  # 用户没有历史订单, 无"不一致"证据
    matched = sum(1 for i in cur_ids if i in hist_ids)
    return round(matched / len(cur_ids), 4)


async def _feat_trip_blacklist_passport_count(db: AsyncSession, order_id: str) -> float:
    """本单乘客证件命中 risk_blacklist(护照号) 的数量 — R030"""
    cur_ids = list((await db.execute(
        select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
    )).scalars().all())
    if not cur_ids:
        return 0.0
    bl_values = set((await db.execute(
        select(RiskBlacklist.blacklist_value).where(
            RiskBlacklist.blacklist_type == "护照号",
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalars().all())
    return float(sum(1 for i in cur_ids if i in bl_values))


async def _feat_trip_same_flight_1h(db: AsyncSession, order_id: str) -> float:
    """同一用户 1 小时内预订同航班的数量(含本单) — R008 黄牛囤票"""
    user_id = await _get_user_by_order(db, order_id)
    if not user_id:
        return 0.0
    flight_nos = set((await db.execute(
        select(BookingFlight.flight_no).where(BookingFlight.order_id == order_id)
    )).scalars().all())
    if not flight_nos:
        return 0.0
    order_time = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not order_time or not order_time.create_time:
        return 0.0
    t = order_time.create_time
    stmt = (
        select(func.count())
        .select_from(BookingFlight)
        .join(OrderInfo, BookingFlight.order_id == OrderInfo.order_id)
        .where(
            OrderInfo.user_id == user_id,
            BookingFlight.flight_no.in_(list(flight_nos)),
            OrderInfo.create_time >= t - timedelta(hours=1),
            OrderInfo.create_time <= t + timedelta(hours=1),
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_trip_distinct_passenger_count(db: AsyncSession, order_id: str) -> float:
    """用户历史去重乘客证件数 — R032"""
    user_id = await _get_user_by_order(db, order_id)
    if not user_id:
        return 0.0
    stmt = (
        select(func.count(func.distinct(PassengerInfo.id_number)))
        .select_from(PassengerInfo)
        .join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == user_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_trip_visa_apply_30d(db: AsyncSession, order_id: str) -> float:
    """用户近 30 天签证申请次数 (辅助 R002)"""
    user_id = await _get_user_by_order(db, order_id)
    if not user_id:
        return 0.0
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(VisaApplication).where(
        VisaApplication.user_id == user_id,
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_trip_same_hotel_1h(db: AsyncSession, order_id: str) -> float:
    """同一用户 1 小时内预订同酒店的数量(含本单) — R034 酒店倒卖"""
    user_id = await _get_user_by_order(db, order_id)
    if not user_id:
        return 0.0
    hotel_ids = set((await db.execute(
        select(BookingHotel.hotel_id).where(BookingHotel.order_id == order_id)
    )).scalars().all())
    if not hotel_ids:
        return 0.0
    order_time = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not order_time or not order_time.create_time:
        return 0.0
    t = order_time.create_time
    stmt = (
        select(func.count())
        .select_from(BookingHotel)
        .join(OrderInfo, BookingHotel.order_id == OrderInfo.order_id)
        .where(
            OrderInfo.user_id == user_id,
            BookingHotel.hotel_id.in_(list(hotel_ids)),
            OrderInfo.create_time >= t - timedelta(hours=1),
            OrderInfo.create_time <= t + timedelta(hours=1),
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 分类聚合 (字典派发)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 11 个用户维度特征 (total_orders 预查一次, 派生特征复用)"""
    total_orders = await _feat_user_total_orders(db, user_id)
    features = {
        "user_total_orders": total_orders,
        "user_orders_7d": await _feat_user_orders_7d(db, user_id),
        "user_orders_30d": await _feat_user_orders_30d(db, user_id),
        "user_total_amount": await _feat_user_total_amount(db, user_id),
        "user_avg_order_amount": await _feat_user_avg_order_amount(db, user_id, total_orders),
        "user_max_order_amount": await _feat_user_max_order_amount(db, user_id),
        "user_visa_reject_90d": await _feat_user_visa_reject_90d(db, user_id),
        "user_visa_countries_30d": await _feat_user_visa_countries_30d(db, user_id),
        "user_account_age_days": await _feat_user_account_age_days(db, user_id),
        "user_real_name_status": await _feat_user_real_name_status(db, user_id),
        "user_refund_rate": await _feat_user_refund_rate(db, user_id, total_orders),
    }
    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个订单维度特征"""
    return {
        "order_total_amount": await _feat_order_total_amount(db, order_id),
        "order_is_night": await _feat_order_is_night(db, order_id),
        "order_trip_days": await _feat_order_trip_days(db, order_id),
        "order_passenger_count": await _feat_order_passenger_count(db, order_id),
        "order_is_overseas": await _feat_order_is_overseas(db, order_id),
        "order_is_flight": await _feat_order_is_flight(db, order_id),
        "order_booking_count": await _feat_order_booking_count(db, order_id),
        "order_is_urgent": await _feat_order_is_urgent(db, order_id),
    }


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算 6 个行程/乘客维度特征 (Q5: 沿用 decision.py 归类到"地址"实体标签)"""
    if not receive_id:
        return {}
    order_id = receive_id  # 调用方约定: 行程特征用 receive_id 槽位传 order_id
    return {
        "trip_passenger_match_rate": await _feat_trip_passenger_match_rate(db, order_id),
        "trip_blacklist_passport_count": await _feat_trip_blacklist_passport_count(db, order_id),
        "trip_same_flight_1h": await _feat_trip_same_flight_1h(db, order_id),
        "trip_distinct_passenger_count": await _feat_trip_distinct_passenger_count(db, order_id),
        "trip_visa_apply_30d": await _feat_trip_visa_apply_30d(db, order_id),
        "trip_same_hotel_1h": await _feat_trip_same_hotel_1h(db, order_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回.
    约定: 旅游项目无收货地址概念, receive_id 槽位复用为 order_id,
    保证 decision.py 的 7 步流水线签名与流程零改动 (Q5)."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id or order_id))
    return features


# ============================================================
# 特征元数据 (供规则编辑器的"傻瓜式"条件构建器使用)
# 顺序与 FEATURE_COLUMNS 一致; type: int=数值 / binary=是/否 / ratio=0-1 比率
# ============================================================
FEATURE_META: list[dict] = [
    {"field": "user_total_orders", "label": "历史订单数", "type": "int"},
    {"field": "user_orders_30d", "label": "近30天订单数", "type": "int"},
    {"field": "user_orders_7d", "label": "近7天订单数", "type": "int"},
    {"field": "user_total_amount", "label": "累计消费金额", "type": "int"},
    {"field": "user_avg_order_amount", "label": "平均订单金额", "type": "int"},
    {"field": "user_max_order_amount", "label": "最大单笔金额", "type": "int"},
    {"field": "user_visa_reject_90d", "label": "90天拒签次数", "type": "int"},
    {"field": "user_visa_countries_30d", "label": "30天申请签证国家数", "type": "int"},
    {"field": "user_account_age_days", "label": "账号年龄(天)", "type": "int"},
    {"field": "user_real_name_status", "label": "是否实名", "type": "binary"},
    {"field": "user_refund_rate", "label": "退改率", "type": "ratio"},
    {"field": "order_total_amount", "label": "订单金额", "type": "int"},
    {"field": "order_is_night", "label": "是否凌晨下单(1-5点)", "type": "binary"},
    {"field": "order_trip_days", "label": "行程天数", "type": "int"},
    {"field": "order_passenger_count", "label": "订单乘客数", "type": "int"},
    {"field": "order_is_overseas", "label": "是否跨境订单", "type": "binary"},
    {"field": "order_is_flight", "label": "是否机票订单", "type": "binary"},
    {"field": "order_booking_count", "label": "关联航班+酒店数", "type": "int"},
    {"field": "order_is_urgent", "label": "是否临近出行(<7天)", "type": "binary"},
    {"field": "trip_passenger_match_rate", "label": "乘客证件匹配率", "type": "ratio"},
    {"field": "trip_blacklist_passport_count", "label": "黑护照数量", "type": "int"},
    {"field": "trip_same_flight_1h", "label": "1小时同航班预订数", "type": "int"},
    {"field": "trip_distinct_passenger_count", "label": "历史去重乘客数", "type": "int"},
    {"field": "trip_visa_apply_30d", "label": "30天签证申请数", "type": "int"},
    {"field": "trip_same_hotel_1h", "label": "1小时同酒店预订数", "type": "int"},
]


# ============================================================
# Demo: 展示 25 维特征名 — 无需 DB
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 25 维旅游风控特征名")
    print("=" * 60)
    groups = [
        ("用户 (11)", [
            "user_total_orders", "user_orders_7d", "user_orders_30d",
            "user_total_amount", "user_avg_order_amount", "user_max_order_amount",
            "user_visa_reject_90d", "user_visa_countries_30d",
            "user_account_age_days", "user_real_name_status", "user_refund_rate",
        ]),
        ("订单 (8)", [
            "order_total_amount", "order_is_night", "order_trip_days",
            "order_passenger_count", "order_is_overseas", "order_is_flight",
            "order_booking_count", "order_is_urgent",
        ]),
        ("行程/乘客 (6)", [
            "trip_passenger_match_rate", "trip_blacklist_passport_count",
            "trip_same_flight_1h", "trip_distinct_passenger_count",
            "trip_visa_apply_30d", "trip_same_hotel_1h",
        ]),
    ]
    total = 0
    for sec, feats in groups:
        print(f"\n【{sec}】")
        for i, k in enumerate(feats, 1):
            print(f"  {i:>2}. {k}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost FEATURE_COLUMNS 一一对应)")
