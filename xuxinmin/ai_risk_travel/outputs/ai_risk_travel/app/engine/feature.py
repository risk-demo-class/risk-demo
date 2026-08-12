"""
旅游风控系统 - 特征工程模块

通过 ORM 查询旅游业务表, 计算 25 个风控特征 (3 大特征族):
  user_*  用户族 (14): 订单量 / 金额 / 退改 / 拒签 / 目的地 / 实名 / 账号年龄
  order_* 订单族 (7):  金额 / 乘客数 / 行程天数 / 深夜下单 / 紧急行程 / 目的地 / 航班数
  pax_*   乘客族 (4):  证件一致性 / 证件撞黑 / 外籍乘客 / 平均年龄

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type:
  user_xxx  → 用户    order_xxx → 订单    pax_xxx → 乘客
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingFlight,
    OrderInfo,
    PassengerInfo,
    RiskBlacklist,
    UserInfo,
    VisaApplication,
)


# 通用 SQL 工具
async def _count(db: AsyncSession, model: type, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(db: AsyncSession, model: type, col_name: str, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (14 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史订单总数"""
    return await _count(db, OrderInfo, user_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天订单数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天订单数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史总消费金额"""
    return await _sum(db, OrderInfo, "total_amount", user_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均订单金额 = 总金额 / 订单数. total_orders 预传可避免重复查 SQL."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔订单金额"""
    stmt = select(func.coalesce(func.max(OrderInfo.total_amount), 0)).where(
        OrderInfo.user_id == user_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """退改签次数 (已退订 + 已取消)"""
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.order_status.in_(["已退订", "已取消"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """退改率 = 退改签次数 / 总订单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    refund_count = await _feat_user_refund_count(db, user_id)
    return round(refund_count / total_orders, 4)


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """历史拒签次数 (签证状态=被拒)"""
    return await _count(db, VisaApplication, user_id=user_id, visa_status="被拒")


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    """目的地国家数 (DISTINCT dest_country)"""
    stmt = select(func.count(func.distinct(OrderInfo.dest_country))).select_from(
        OrderInfo,
    ).where(OrderInfo.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visa_reject_count_90d(db: AsyncSession, user_id: str) -> float:
    """近 90 天拒签次数"""
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.count()).select_from(VisaApplication).where(
        VisaApplication.user_id == user_id,
        VisaApplication.visa_status == "被拒",
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visa_countries_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天申请签证的国家数 (DISTINCT)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count(func.distinct(VisaApplication.dest_country))).select_from(
        VisaApplication,
    ).where(
        VisaApplication.user_id == user_id,
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_real_name_status(db: AsyncSession, user_id: str) -> float:
    """是否实名 (0/1)"""
    row = (await db.execute(
        select(UserInfo.real_name_status).where(UserInfo.user_id == user_id)
    )).first()
    return float((row[0] or 0) if row else 0)


async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """账号注册天数"""
    row = (await db.execute(
        select(UserInfo.account_age_days).where(UserInfo.user_id == user_id)
    )).first()
    return float(row[0] if row and row[0] is not None else 0)


# ============================================================
# 订单维度特征 (7 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    row = (await db.execute(
        select(OrderInfo.total_amount).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_order_passenger_count(db: AsyncSession, order_id: str) -> float:
    row = (await db.execute(
        select(OrderInfo.passenger_count).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 1.0


async def _feat_order_trip_days(db: AsyncSession, order_id: str) -> float:
    """出行天数 = 返程 - 出发 (天), 缺任一天返回 0"""
    row = (await db.execute(
        select(OrderInfo.depart_date, OrderInfo.return_date)
        .where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.depart_date and row.return_date:
        delta = row.return_date - row.depart_date
        return max(float(delta.days), 0)
    return 0.0


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否凌晨下单 (1-5 点)"""
    row = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 1 <= row.create_time.hour <= 5 else 0.0
    return 0.0


async def _feat_order_is_urgent(db: AsyncSession, order_id: str) -> float:
    """是否紧急行程: 出发日期 - 下单时间 < 7 天"""
    row = (await db.execute(
        select(OrderInfo.create_time, OrderInfo.depart_date)
        .where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time and row.depart_date:
        lead_days = (row.depart_date - row.create_time).days
        return 1.0 if lead_days < 7 else 0.0
    return 0.0


async def _feat_order_dest_country_count(db: AsyncSession, order_id: str) -> float:
    """用户近 90 天目的地国家数 (上下文特征)"""
    row = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id)
    )).first()
    if not row:
        return 0.0
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.count(func.distinct(OrderInfo.dest_country))).select_from(
        OrderInfo,
    ).where(
        OrderInfo.user_id == row.user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_flight_count(db: AsyncSession, order_id: str) -> float:
    """订单关联的航班预订数"""
    return await _count(db, BookingFlight, order_id=order_id)


# ============================================================
# 乘客维度特征 (4 个)
# ============================================================

async def _feat_pax_id_consistency(db: AsyncSession, user_id: str, order_id: str) -> float:
    """乘客证件一致性: 本单乘客证件号与用户历史订单乘客的匹配率 (0-1)"""
    current_ids = list((await db.execute(
        select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
    )).scalars().all())
    if not current_ids:
        return 0.0
    historical_ids = set((await db.execute(
        select(PassengerInfo.id_number)
        .select_from(PassengerInfo)
        .join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id)
        .where(
            OrderInfo.user_id == user_id,
            OrderInfo.order_id != order_id,
        )
    )).scalars().all())
    matched = sum(1 for cid in current_ids if cid in historical_ids)
    return round(matched / len(current_ids), 4)


async def _feat_pax_blacklist_hits(db: AsyncSession, order_id: str) -> float:
    """乘客证件撞黑次数 (护照号/身份证号黑名单)"""
    ids = list((await db.execute(
        select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
    )).scalars().all())
    if not ids:
        return 0.0
    stmt = select(func.count()).select_from(RiskBlacklist).where(
        RiskBlacklist.blacklist_type.in_(["护照号", "身份证号"]),
        RiskBlacklist.blacklist_value.in_(ids),
        RiskBlacklist.deleted_at.is_(None),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_pax_foreign_nationality_count(db: AsyncSession, order_id: str) -> float:
    """外籍乘客数"""
    stmt = select(func.count()).select_from(PassengerInfo).where(
        PassengerInfo.order_id == order_id,
        PassengerInfo.nationality != "中国",
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_pax_avg_age(db: AsyncSession, order_id: str) -> float:
    """乘客平均年龄"""
    stmt = select(func.coalesce(func.avg(PassengerInfo.age), 0)).where(
        PassengerInfo.order_id == order_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征."""
    total_orders = await _feat_user_total_orders(db, user_id)

    independent_features = {
        "user_orders_30d": _feat_user_orders_30d,
        "user_orders_7d": _feat_user_orders_7d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_refund_count": _feat_user_refund_count,
        "user_complaint_count": _feat_user_complaint_count,
        "user_address_count": _feat_user_address_count,
        "user_visa_reject_count_90d": _feat_user_visa_reject_count_90d,
        "user_visa_countries_30d": _feat_user_visa_countries_30d,
        "user_real_name_status": _feat_user_real_name_status,
        "user_account_age_days": _feat_user_account_age_days,
    }
    features = {name: await fn(db, user_id) for name, fn in independent_features.items()}
    features["user_total_orders"] = total_orders
    # 派生特征: 传 total_orders 避免再查
    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(
        db, user_id, total_orders=total_orders,
    )
    features["user_refund_rate"] = await _feat_user_refund_rate(
        db, user_id, total_orders=total_orders,
    )
    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 7 个订单维度特征."""
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_passenger_count": _feat_order_passenger_count,
        "order_trip_days": _feat_order_trip_days,
        "order_is_night": _feat_order_is_night,
        "order_is_urgent": _feat_order_is_urgent,
        "order_dest_country_count": _feat_order_dest_country_count,
        "order_flight_count": _feat_order_flight_count,
    }
    return {name: await fn(db, order_id) for name, fn in feat_funcs.items()}


async def compute_passenger_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
) -> dict[str, float]:
    """计算 4 个乘客维度特征."""
    if not order_id:
        return {
            "pax_id_consistency": 0.0,
            "pax_blacklist_hits": 0.0,
            "pax_foreign_nationality_count": 0.0,
            "pax_avg_age": 0.0,
        }
    return {
        "pax_id_consistency": await _feat_pax_id_consistency(db, user_id, order_id),
        "pax_blacklist_hits": await _feat_pax_blacklist_hits(db, order_id),
        "pax_foreign_nationality_count": await _feat_pax_foreign_nationality_count(db, order_id),
        "pax_avg_age": await _feat_pax_avg_age(db, order_id),
    }


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """兼容基线函数名: 旅游行业没有收货地址, 这里退化为乘客特征 (无订单时返回空)."""
    return await compute_passenger_features(db, user_id, order_id=receive_id)


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 25 个特征并合并返回."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
        features.update(await compute_passenger_features(db, user_id, order_id))
    else:
        # 无订单 (签证申请场景): 乘客族全 0
        features.update(await compute_passenger_features(db, user_id, None))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 (无需 DB)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("旅游风控特征工程 — 25 维特征名 + 字典派发表")
    print("=" * 60)

    user_feats = [
        ("user_total_orders",          "历史订单总数"),
        ("user_orders_30d",            "近 30 天订单数"),
        ("user_orders_7d",             "近 7 天订单数"),
        ("user_total_amount",          "历史总消费金额"),
        ("user_avg_order_amount",      "平均订单金额"),
        ("user_max_order_amount",      "最大单笔订单金额"),
        ("user_refund_count",          "退改签次数(已退订+已取消)"),
        ("user_refund_rate",           "退改率"),
        ("user_complaint_count",       "历史拒签次数"),
        ("user_address_count",         "目的地国家数"),
        ("user_visa_reject_count_90d", "近90天拒签次数"),
        ("user_visa_countries_30d",    "近30天申请签证国家数"),
        ("user_real_name_status",      "是否实名(0/1)"),
        ("user_account_age_days",      "账号注册天数"),
    ]
    order_feats = [
        ("order_total_amount",    "订单总金额"),
        ("order_passenger_count", "乘客数"),
        ("order_trip_days",       "出行天数"),
        ("order_is_night",        "是否凌晨下单(1-5点)"),
        ("order_is_urgent",       "是否紧急行程(<7天出发)"),
        ("order_dest_country_count", "近90天目的地国家数"),
        ("order_flight_count",    "订单关联航班数"),
    ]
    pax_feats = [
        ("pax_id_consistency",          "乘客证件与历史匹配率"),
        ("pax_blacklist_hits",          "乘客证件撞黑次数"),
        ("pax_foreign_nationality_count", "外籍乘客数"),
        ("pax_avg_age",                 "乘客平均年龄"),
    ]
    all_groups = [
        ("用户 (14)", user_feats),
        ("订单 (7)", order_feats),
        ("乘客 (4)", pax_feats),
    ]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<30} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
