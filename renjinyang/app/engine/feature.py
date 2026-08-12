"""旅游 OTA 风控特征工程。

对外仍输出历史模型约定的 25 个键，避免修改 ``FEATURE_COLUMNS`` 和模型文件格式；
每个旧键在本模块中被赋予旅游业务语义，具体映射见各函数中文说明。
"""
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    RiskEvent,
    UserInfo,
    VisaApplication,
)


async def _scalar(db: AsyncSession, stmt, default=0) -> float:
    """执行单值查询并安全转换为浮点数。"""
    value = (await db.execute(stmt)).scalar()
    return float(default if value is None else value)


# ============================================================
# 用户维度（14 个）
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史旅游订单总数。"""
    return await _scalar(db, select(func.count()).select_from(OrderInfo).where(OrderInfo.user_id == user_id))


async def _orders_since(db: AsyncSession, user_id: str, days: int) -> float:
    """统计最近若干天内的旅游订单数。"""
    return await _scalar(db, select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.book_time >= datetime.now() - timedelta(days=days),
    ))


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天订单数。"""
    return await _orders_since(db, user_id, 30)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天订单数。"""
    return await _orders_since(db, user_id, 7)


async def _amount_aggregate(db: AsyncSession, user_id: str, aggregate) -> float:
    """按用户聚合旅游订单金额。"""
    return await _scalar(db, select(func.coalesce(aggregate(OrderInfo.total_amount), 0)).where(
        OrderInfo.user_id == user_id
    ))


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史旅游消费总额。"""
    return await _amount_aggregate(db, user_id, func.sum)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """历史旅游订单平均金额；可复用预计算订单数以减少查询。"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if not total_orders:
        return 0.0
    return round(await _feat_user_total_amount(db, user_id) / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """历史最大单笔旅游订单金额。"""
    return await _amount_aggregate(db, user_id, func.max)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """历史退改申请次数；复用旧 ``user_refund_count`` 键。"""
    return await _scalar(db, select(func.count()).select_from(RiskEvent).where(
        RiskEvent.user_id == user_id,
        RiskEvent.event_type == "售后申请",  # 旅游“退改申请”的核心表兼容枚举
    ))


async def _feat_user_postsale_count(db: AsyncSession, user_id: str) -> float:
    """近 90 天累计拒签历史次数；用于拒签历史拦截规则。"""
    return await _scalar(db, select(func.coalesce(func.sum(VisaApplication.reject_history), 0)).where(
        VisaApplication.user_id == user_id,
        VisaApplication.submit_time >= datetime.now() - timedelta(days=90),
    ))


async def _feat_user_refund_rate(db: AsyncSession, user_id: str, total_orders: float) -> float:
    """退改率 = 退改申请次数 / 历史订单数。"""
    return round(await _feat_user_refund_count(db, user_id) / total_orders, 4) if total_orders else 0.0


async def _feat_user_postsale_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """拒签风险率 = 近 90 天拒签次数 / 历史订单数。"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if not total_orders:
        return 0.0
    return round(await _feat_user_postsale_count(db, user_id) / total_orders, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    """实名状态编码：未实名=0、已实名=1、已认证=2。

    旅游业务没有退款金额字段，因此复用旧 ``user_refund_amount`` 键承载实名
    强度，使模型可以学习“新账户 + 未实名 + 大额订单”的组合风险。
    """
    status = (await db.execute(select(UserInfo.real_name_status).where(
        UserInfo.user_id == user_id
    ))).scalar_one_or_none()
    return float({"未实名": 0, "已实名": 1, "已认证": 2}.get(status, 0))


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """近 30 天签证申请涉及的不同目的国数；用于短期多国签证规则。"""
    return await _scalar(db, select(func.count(func.distinct(VisaApplication.dest_country))).where(
        VisaApplication.user_id == user_id,
        VisaApplication.submit_time >= datetime.now() - timedelta(days=30),
    ))


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """该用户乘客证件命中有效业务黑名单的数量。

    项目没有独立投诉表，因此复用旧 ``user_complaint_count`` 键承载更重要的
    旅游证件风险信号，并供“黑护照拦截”规则使用。
    """
    now = datetime.now()
    return await _scalar(db, select(func.count(func.distinct(PassengerInfo.id_number))).select_from(
        PassengerInfo
    ).join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id).join(
        BlacklistExtra,
        and_(BlacklistExtra.type == "护照号", BlacklistExtra.value == PassengerInfo.id_number),
    ).where(
        OrderInfo.user_id == user_id,
        PassengerInfo.id_type == "护照",
        or_(BlacklistExtra.expire_at.is_(None), BlacklistExtra.expire_at > now),
    ))


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    """历史不同乘客证件数量；复用旧地址数量键。"""
    return await _scalar(db, select(func.count(func.distinct(PassengerInfo.id_number))).select_from(
        PassengerInfo
    ).join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id).where(OrderInfo.user_id == user_id))


# ============================================================
# 订单维度（8 个）
# ============================================================

async def _order_row(db: AsyncSession, order_id: str):
    """读取当前旅游订单；不存在时返回 ``None``。"""
    return (await db.execute(select(OrderInfo).where(OrderInfo.order_id == order_id))).scalar_one_or_none()


async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """当前订单总金额。"""
    return await _scalar(db, select(OrderInfo.total_amount).where(OrderInfo.order_id == order_id))


async def _feat_order_item_count(db: AsyncSession, order_id: str) -> float:
    """当前订单声明的乘客或入住人数。"""
    return await _scalar(db, select(OrderInfo.passenger_count).where(OrderInfo.order_id == order_id))


async def _feat_order_sku_count(db: AsyncSession, order_id: str) -> float:
    """同一用户一小时内预订同一航班的累计票数；用于识别黄牛囤票。"""
    row = (await db.execute(select(
        OrderInfo.user_id, OrderInfo.book_time, BookingFlight.flight_no,
    ).select_from(OrderInfo).join(
        BookingFlight, BookingFlight.order_id == OrderInfo.order_id
    ).where(OrderInfo.order_id == order_id))).first()
    if not row:
        return 0.0
    start = row.book_time - timedelta(hours=1)
    end = row.book_time + timedelta(hours=1)
    return await _scalar(db, select(func.coalesce(func.sum(OrderInfo.passenger_count), 0)).select_from(
        OrderInfo
    ).join(BookingFlight, BookingFlight.order_id == OrderInfo.order_id).where(
        OrderInfo.user_id == row.user_id,
        BookingFlight.flight_no == row.flight_no,
        OrderInfo.book_time.between(start, end),
    ))


async def _feat_order_discount_amount(db: AsyncSession, order_id: str) -> float:
    """下单用户的账户注册天数；用于新用户大单识别。"""
    return await _scalar(db, select(UserInfo.account_age_days).select_from(OrderInfo).join(
        UserInfo, UserInfo.user_id == OrderInfo.user_id
    ).where(OrderInfo.order_id == order_id))


async def _feat_order_discount_rate(db: AsyncSession, order_id: str) -> float:
    """本单乘客证件与该用户历史乘客证件的匹配比例（0～1）。"""
    order = await _order_row(db, order_id)
    if not order:
        return 0.0
    current = set((await db.execute(select(PassengerInfo.id_number).where(
        PassengerInfo.order_id == order_id
    ))).scalars().all())
    if not current:
        return 0.0
    history = set((await db.execute(select(PassengerInfo.id_number).select_from(
        PassengerInfo
    ).join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id).where(
        OrderInfo.user_id == order.user_id,
        OrderInfo.order_id != order_id,
    ))).scalars().all())
    return round(len(current & history) / len(current), 4)


async def _feat_order_pay_interval(db: AsyncSession, order_id: str) -> float:
    """提前预订天数；复用旧支付间隔键。"""
    row = (await db.execute(select(OrderInfo.book_time, OrderInfo.depart_date).where(
        OrderInfo.order_id == order_id
    ))).first()
    return float(max((row.depart_date - row.book_time.date()).days, 0)) if row else 0.0


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否在凌晨 1:00（含）至 5:00（不含）突击下单。"""
    book_time = (await db.execute(select(OrderInfo.book_time).where(
        OrderInfo.order_id == order_id
    ))).scalar_one_or_none()
    return 1.0 if book_time and 1 <= book_time.hour < 5 else 0.0


async def _feat_order_category_count(db: AsyncSession, order_id: str) -> float:
    """行程天数；酒店优先使用入住/离店日期，其他订单使用出发/返回日期。"""
    hotel = (await db.execute(select(BookingHotel.check_in, BookingHotel.check_out).where(
        BookingHotel.order_id == order_id
    ))).first()
    if hotel:
        return float(max((hotel.check_out - hotel.check_in).days, 0))
    row = (await db.execute(select(OrderInfo.depart_date, OrderInfo.return_date).where(
        OrderInfo.order_id == order_id
    ))).first()
    return float(max((row.return_date - row.depart_date).days, 0)) if row else 0.0


# ============================================================
# 目的地维度（3 个，沿用 addr_ 前缀以兼容快照分类）
# ============================================================

async def _feat_addr_total_count(db: AsyncSession, user_id: str) -> float:
    """用户历史有目的地的订单数量。"""
    return await _scalar(db, select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.dest_country.is_not(None),
    ))


async def _feat_addr_province_count(db: AsyncSession, user_id: str) -> float:
    """用户历史不同目的国家或地区数量。"""
    return await _scalar(db, select(func.count(func.distinct(OrderInfo.dest_country))).where(
        OrderInfo.user_id == user_id
    ))


async def _feat_addr_is_new(db: AsyncSession, user_id: str, destination: str | None) -> float:
    """当前目的地是否首次出现；当前订单已落业务库，因此出现不超过一次算新。"""
    if not destination:
        return 0.0
    count = await _scalar(db, select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.dest_country == destination,
    ))
    return 1.0 if count <= 1 else 0.0


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征。"""
    total_orders = await _feat_user_total_orders(db, user_id)
    return {
        "user_total_orders": total_orders,
        "user_orders_30d": await _feat_user_orders_30d(db, user_id),
        "user_orders_7d": await _feat_user_orders_7d(db, user_id),
        "user_total_amount": await _feat_user_total_amount(db, user_id),
        "user_avg_order_amount": await _feat_user_avg_order_amount(db, user_id, total_orders),
        "user_max_order_amount": await _feat_user_max_order_amount(db, user_id),
        "user_refund_count": await _feat_user_refund_count(db, user_id),
        "user_postsale_count": await _feat_user_postsale_count(db, user_id),
        "user_refund_rate": await _feat_user_refund_rate(db, user_id, total_orders),
        "user_postsale_rate": await _feat_user_postsale_rate(db, user_id, total_orders),
        "user_refund_amount": await _feat_user_refund_amount(db, user_id),
        "user_cancel_count": await _feat_user_cancel_count(db, user_id),
        "user_complaint_count": await _feat_user_complaint_count(db, user_id),
        "user_address_count": await _feat_user_address_count(db, user_id),
    }


async def compute_order_features(db: AsyncSession, order_id: str | None) -> dict[str, float]:
    """计算 8 个订单维度特征；无关联订单时返回完整的零值特征。"""
    names = {
        "order_total_amount": _feat_order_total_amount,
        "order_item_count": _feat_order_item_count,
        "order_sku_count": _feat_order_sku_count,
        "order_discount_amount": _feat_order_discount_amount,
        "order_discount_rate": _feat_order_discount_rate,
        "order_pay_interval_sec": _feat_order_pay_interval,
        "order_is_night": _feat_order_is_night,
        "order_category_count": _feat_order_category_count,
    }
    if not order_id:
        return {name: 0.0 for name in names}
    return {name: await function(db, order_id) for name, function in names.items()}


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个目的地特征；``receive_id`` 在旅游链路中承载目的地。"""
    return {
        "addr_total_count": await _feat_addr_total_count(db, user_id),
        "addr_province_count": await _feat_addr_province_count(db, user_id),
        "addr_is_new": await _feat_addr_is_new(db, user_id, receive_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算并返回固定 25 维旅游风控特征。"""
    features = await compute_user_features(db, user_id)
    features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features
