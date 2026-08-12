"""
特征工程模块: 通过 ORM 查询旅游业务数据, 计算 28 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx      = 用户维度特征
  order_xxx     = 订单(旅游订单)维度特征
  traveler_xxx  = 出行人维度特征
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingDetail,
    BookingInfo,
    BookingTraveler,
    ClaimInfo,
    ComplaintInfo,
    PaymentInfo,
    ProductInfo,
    RefundChange,
    ReviewInfo,
    TravelerInfo,
    UserDevice,
)


# 通用 SQL 工具
async def _count(model, db: AsyncSession, **filters) -> float:
    """SELECT COUNT(*) FROM model WHERE filters."""
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(SUM(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (16 个)
# ============================================================

async def _feat_user_total_bookings(db: AsyncSession, user_id: str) -> float:
    """历史旅游订单总数"""
    return await _count(BookingInfo, db, user_id=user_id)


async def _feat_user_bookings_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天下单数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(BookingInfo).where(
        BookingInfo.user_id == user_id,
        BookingInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_bookings_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天下单数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(BookingInfo).where(
        BookingInfo.user_id == user_id,
        BookingInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史总消费金额"""
    stmt = select(func.coalesce(func.sum(BookingDetail.final_amount), 0)).select_from(
        BookingDetail
    ).join(BookingInfo, BookingDetail.booking_id == BookingInfo.booking_id).where(
        BookingInfo.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_bookings: float | None = None,
) -> float:
    """平均订单金额 = 总金额 / 订单数."""
    if total_bookings is None:
        total_bookings = await _feat_user_total_bookings(db, user_id)
    if total_bookings == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_bookings, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔订单金额 (订单分组求和再 MAX)"""
    subq = (
        select(
            BookingDetail.booking_id,
            func.sum(BookingDetail.final_amount).label("booking_total"),
        )
        .join(BookingInfo, BookingDetail.booking_id == BookingInfo.booking_id)
        .where(BookingInfo.user_id == user_id)
        .group_by(BookingDetail.booking_id)
        .subquery()
    )
    stmt = select(func.coalesce(func.max(subq.c.booking_total), 0))
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_change_count(db: AsyncSession, user_id: str) -> float:
    """退改总次数 (退订+改期+部分退款)"""
    stmt = select(func.count()).select_from(RefundChange).join(
        BookingInfo, RefundChange.booking_id == BookingInfo.booking_id
    ).where(BookingInfo.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_bookings: float | None = None,
) -> float:
    """退改率 = 退改次数 / 总订单数."""
    if total_bookings is None:
        total_bookings = await _feat_user_total_bookings(db, user_id)
    if total_bookings == 0:
        return 0
    refund_count = await _feat_user_refund_change_count(db, user_id)
    return round(refund_count / total_bookings, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    """退改总金额"""
    stmt = select(func.coalesce(func.sum(RefundChange.refund_amount), 0)).select_from(
        RefundChange
    ).join(
        BookingInfo, RefundChange.booking_id == BookingInfo.booking_id
    ).where(
        BookingInfo.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_claim_count(db: AsyncSession, user_id: str) -> float:
    """理赔总次数"""
    return await _count(ClaimInfo, db, user_id=user_id)


async def _feat_user_claim_rate(
    db: AsyncSession, user_id: str, total_bookings: float | None = None,
) -> float:
    """理赔率 = 理赔次数 / 总订单数."""
    if total_bookings is None:
        total_bookings = await _feat_user_total_bookings(db, user_id)
    if total_bookings == 0:
        return 0
    claim_count = await _feat_user_claim_count(db, user_id)
    return round(claim_count / total_bookings, 4)


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """投诉次数"""
    return await _count(ComplaintInfo, db, user_id=user_id)


async def _feat_user_traveler_count(db: AsyncSession, user_id: str) -> float:
    """累计出行人数 (该用户名下所有出行人)"""
    return await _count(TravelerInfo, db, user_id=user_id)


async def _feat_user_device_count(db: AsyncSession, user_id: str) -> float:
    """绑定设备数"""
    return await _count(UserDevice, db, user_id=user_id)


async def _feat_user_review_count(db: AsyncSession, user_id: str) -> float:
    """点评次数"""
    return await _count(ReviewInfo, db, user_id=user_id)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """取消订单次数 (booking_status='已取消' 或 '已退订')"""
    stmt = select(func.count()).select_from(BookingInfo).where(
        BookingInfo.user_id == user_id,
        BookingInfo.booking_status.in_(["已取消", "已退订"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 订单维度特征 (9 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, booking_id: str) -> float:
    """订单总金额 (实付合计)"""
    return await _sum(BookingDetail, "final_amount", db, booking_id=booking_id)


async def _feat_order_item_count(db: AsyncSession, booking_id: str) -> float:
    """订单产品行数"""
    stmt = select(func.count()).select_from(BookingDetail).where(BookingDetail.booking_id == booking_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_traveler_count(db: AsyncSession, booking_id: str) -> float:
    """订单出行人数"""
    return await _count(BookingTraveler, db, booking_id=booking_id)


async def _feat_order_discount_rate(db: AsyncSession, booking_id: str) -> float:
    """折扣率 = 优惠金额 / 原总金额"""
    discount = await _sum(BookingDetail, "discount_amount", db, booking_id=booking_id)
    original = await _sum(BookingDetail, "total_amount", db, booking_id=booking_id)
    if original == 0:
        return 0
    return round(discount / original, 4)


async def _feat_order_pay_interval(db: AsyncSession, booking_id: str) -> float:
    """下单到支付时间差 (秒), 未支付返回 -1"""
    row = (await db.execute(
        select(BookingInfo.create_time, BookingInfo.payment_time).where(BookingInfo.booking_id == booking_id)
    )).first()
    if row and row.payment_time and row.create_time:
        return max(float((row.payment_time - row.create_time).total_seconds()), 0)
    return -1


async def _feat_order_is_night(db: AsyncSession, booking_id: str) -> float:
    """是否夜间下单 (0~6 点)"""
    row = (await db.execute(
        select(BookingInfo.create_time).where(BookingInfo.booking_id == booking_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour < 6 else 0.0
    return 0.0


async def _feat_order_lead_days(db: AsyncSession, booking_id: str) -> float:
    """预订提前天数 = 出发时间 - 下单时间 (天). 负数/0 表示临期或已出发"""
    row = (await db.execute(
        select(BookingInfo.create_time, BookingInfo.departure_time).where(BookingInfo.booking_id == booking_id)
    )).first()
    if row and row.create_time and row.departure_time:
        return round((row.departure_time - row.create_time).total_seconds() / 86400, 2)
    return 0.0


async def _feat_order_trip_days(db: AsyncSession, booking_id: str) -> float:
    """行程天数 = 结束时间 - 出发时间 (天). 无结束时间用产品行程天数"""
    row = (await db.execute(
        select(BookingInfo.departure_time, BookingInfo.end_time).where(BookingInfo.booking_id == booking_id)
    )).first()
    if row and row.departure_time and row.end_time:
        return max(round((row.end_time - row.departure_time).total_seconds() / 86400, 2), 1)
    if row and row.departure_time:
        return 1.0
    return 1.0


async def _feat_order_is_overseas(db: AsyncSession, booking_id: str) -> float:
    """订单是否出境游 (任一产品为出境游即 1)"""
    stmt = select(func.coalesce(func.max(ProductInfo.is_overseas), 0)).select_from(
        BookingDetail
    ).join(ProductInfo, BookingDetail.product_id == ProductInfo.product_id).where(
        BookingDetail.booking_id == booking_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 出行人维度特征 (3 个)
# ============================================================

async def _feat_traveler_total_count(db: AsyncSession, booking_id: str) -> float:
    """本次订单出行人总数"""
    return await _count(BookingTraveler, db, booking_id=booking_id)


async def _feat_traveler_phone_count(db: AsyncSession, booking_id: str) -> float:
    """本次订单不同出行人手机号数 (去重, 空手机号不算)"""
    stmt = select(func.count(func.distinct(TravelerInfo.phone))).select_from(
        BookingTraveler
    ).join(TravelerInfo, BookingTraveler.traveler_id == TravelerInfo.traveler_id).where(
        BookingTraveler.booking_id == booking_id,
        TravelerInfo.phone.isnot(None),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_traveler_new_count(
    db: AsyncSession, booking_id: str, user_id: str,
) -> float:
    """本次订单"新出行人"数量 = 未在该用户历史其他订单中出现过的出行人数"""
    # 1. 本单出行人
    cur = (await db.execute(
        select(BookingTraveler.traveler_id).where(BookingTraveler.booking_id == booking_id)
    )).scalars().all()
    if not cur:
        return 0.0
    cur_set = set(cur)

    # 2. 该用户其他订单的出行人
    subq = (
        select(BookingInfo.booking_id)
        .where(BookingInfo.user_id == user_id, BookingInfo.booking_id != booking_id)
        .subquery()
    )
    stmt = select(BookingTraveler.traveler_id).select_from(
        BookingTraveler
    ).join(subq, BookingTraveler.booking_id == subq.c.booking_id)
    old_set = set((await db.execute(stmt)).scalars().all())

    new_count = len(cur_set - old_set)
    return float(new_count)


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 16 个用户维度特征 (total_bookings 一次查询复用于派生特征)."""
    total_bookings = await _feat_user_total_bookings(db, user_id)

    independent_features = {
        "user_bookings_7d": _feat_user_bookings_7d,
        "user_bookings_30d": _feat_user_bookings_30d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_refund_change_count": _feat_user_refund_change_count,
        "user_refund_amount": _feat_user_refund_amount,
        "user_claim_count": _feat_user_claim_count,
        "user_complaint_count": _feat_user_complaint_count,
        "user_traveler_count": _feat_user_traveler_count,
        "user_device_count": _feat_user_device_count,
        "user_review_count": _feat_user_review_count,
        "user_cancel_count": _feat_user_cancel_count,
    }
    features = {name: await func(db, user_id) for name, func in independent_features.items()}
    features["user_total_bookings"] = total_bookings

    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(db, user_id, total_bookings=total_bookings)
    features["user_refund_rate"] = await _feat_user_refund_rate(db, user_id, total_bookings=total_bookings)
    features["user_claim_rate"] = await _feat_user_claim_rate(db, user_id, total_bookings=total_bookings)

    return features


async def compute_order_features(db: AsyncSession, booking_id: str) -> dict[str, float]:
    """计算 9 个订单维度特征."""
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_item_count": _feat_order_item_count,
        "order_traveler_count": _feat_order_traveler_count,
        "order_discount_rate": _feat_order_discount_rate,
        "order_pay_interval_sec": _feat_order_pay_interval,
        "order_is_night": _feat_order_is_night,
        "order_lead_days": _feat_order_lead_days,
        "order_trip_days": _feat_order_trip_days,
        "order_is_overseas": _feat_order_is_overseas,
    }
    return {name: await func(db, booking_id) for name, func in feat_funcs.items()}


async def compute_traveler_features(
    db: AsyncSession,
    booking_id: str | None,
    user_id: str,
) -> dict[str, float]:
    """计算 3 个出行人维度特征 (无订单时全 0)."""
    if not booking_id:
        return {
            "traveler_total_count": 0.0,
            "traveler_phone_count": 0.0,
            "traveler_new_count": 0.0,
        }
    return {
        "traveler_total_count": await _feat_traveler_total_count(db, booking_id),
        "traveler_phone_count": await _feat_traveler_phone_count(db, booking_id),
        "traveler_new_count": await _feat_traveler_new_count(db, booking_id, user_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    booking_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 28 维特征并合并返回."""
    features = await compute_user_features(db, user_id)
    if booking_id:
        features.update(await compute_order_features(db, booking_id))
    features.update(await compute_traveler_features(db, booking_id, user_id))
    return features


# ============================================================
# Demo: 展示 28 维特征名 + 分类 — 无需 DB
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("旅游特征工程 — 28 维特征名")
    print("=" * 60)

    user_feats = [
        ("user_total_bookings",     "历史旅游订单总数"),
        ("user_bookings_7d",        "近 7 天下单数"),
        ("user_bookings_30d",       "近 30 天下单数"),
        ("user_total_amount",       "历史总消费金额"),
        ("user_avg_order_amount",   "平均订单金额"),
        ("user_max_order_amount",   "最大单笔订单金额"),
        ("user_refund_change_count","退改总次数"),
        ("user_refund_rate",        "退改率"),
        ("user_refund_amount",      "退改总金额"),
        ("user_claim_count",        "理赔总次数"),
        ("user_claim_rate",         "理赔率"),
        ("user_complaint_count",    "投诉次数"),
        ("user_traveler_count",     "累计出行人数"),
        ("user_device_count",       "绑定设备数"),
        ("user_review_count",       "点评次数"),
        ("user_cancel_count",       "取消订单次数"),
    ]
    order_feats = [
        ("order_total_amount",      "订单总金额(实付)"),
        ("order_item_count",        "订单产品行数"),
        ("order_traveler_count",    "订单出行人数"),
        ("order_discount_rate",     "折扣率"),
        ("order_pay_interval_sec",  "下单到支付时间差(秒)"),
        ("order_is_night",          "是否夜间下单 (0-6 点)"),
        ("order_lead_days",         "预订提前天数"),
        ("order_trip_days",         "行程天数"),
        ("order_is_overseas",       "是否出境游 (0/1)"),
    ]
    traveler_feats = [
        ("traveler_total_count",    "本次订单出行人总数"),
        ("traveler_phone_count",    "本次订单不同出行人手机号数"),
        ("traveler_new_count",      "本次订单新出行人数"),
    ]
    total = 0
    for sec, feats in [("用户 (16)", user_feats), ("订单 (9)", order_feats), ("出行人 (3)", traveler_feats)]:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<26} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 ml_model.py 的 FEATURE_COLUMNS 顺序一一对应)")
