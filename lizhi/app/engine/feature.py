"""
特征工程模块 (旅游行业版): 通过 ORM 查询业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx  = 用户维度特征
  order_xxx = 订单维度特征
  addr_xxx  = 地址维度特征 → 旅游行业映射为"目的地/行程"维度

三大特征族 (跟任务书任务 3 对齐):
  用户族 (14): 订单活跃度 / 金额 / 退改 / 凌晨下单 / 同航班囤票 / 签证 / 注册时长
  订单族 (8):  金额 / 乘客 / 夜间下单 / 出行间隔 / 行程天数 / 出境 / 同航班窗口 / 新乘客占比
  目的地族 (3): 目的地国家数 / 出境订单占比 / 当前目的地是否去过

⚠️ 特征名与 app/engine/ml_model.py::FEATURE_COLUMNS 一一对应, 改这里必须同步改那边.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingFlight,
    OrderInfo,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)

# 国内目的地集合 (用于 order_is_international / addr_international_order_rate)
DOMESTIC_DESTS = {
    "北京", "上海", "三亚", "成都", "昆明", "西安", "哈尔滨",
    "厦门", "大理", "张家界", "广州", "深圳",
}


# ============================================================
# 通用 SQL 工具
# ============================================================
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
# 用户维度特征 (14 个)
# ============================================================
async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史订单总数"""
    return await _count(OrderInfo, db, user_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天订单数 (突击下单 / 高频囤票信号)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史消费总额 (订单总金额)"""
    return await _sum(OrderInfo, "total_amount", db, user_id=user_id)


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


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """已取消订单数 (占座不付款 / 恶意取消)"""
    return await _count(OrderInfo, db, user_id=user_id, order_status="已取消")


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """退改次数 (订单状态=已退改, 对应电商版"退款次数")"""
    return await _count(OrderInfo, db, user_id=user_id, order_status="已退改")


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """退改率 = 退改次数 / 总订单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    return round(await _feat_user_refund_count(db, user_id) / total_orders, 4)


async def _feat_user_night_order_count(db: AsyncSession, user_id: str) -> float:
    """凌晨 1-5 点下单数 (0 点突击下单信号)"""
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        func.hour(OrderInfo.create_time).between(1, 5),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_same_flight_1h_count(db: AsyncSession, user_id: str) -> float:
    """同航班 1 小时窗口最大预订数 (黄牛囤票: 同一航班同一小时被订几次)"""
    subq = (
        select(
            BookingFlight.flight_no,
            func.date(OrderInfo.create_time).label("d"),
            func.hour(OrderInfo.create_time).label("h"),
            func.count().label("c"),
        )
        .join(OrderInfo, BookingFlight.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == user_id)
        .group_by(BookingFlight.flight_no, text("d"), text("h"))
        .subquery()
    )
    stmt = select(func.coalesce(func.max(subq.c.c), 0))
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visa_apply_count(db: AsyncSession, user_id: str) -> float:
    """签证申请总数"""
    return await _count(VisaApplication, db, user_id=user_id)


async def _feat_user_visa_reject_count(db: AsyncSession, user_id: str) -> float:
    """拒签次数 (状态=拒签, 对应任务书 R001 拒签历史拦截)"""
    return await _count(VisaApplication, db, user_id=user_id, status="拒签")


async def _feat_user_visa_multi_country_30d(db: AsyncSession, user_id: str) -> float:
    """30 天内申请的不同国家数 (短期多国签证信号)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count(func.distinct(VisaApplication.dest_country))).where(
        VisaApplication.user_id == user_id,
        VisaApplication.submit_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """注册时长(天), 新用户大单信号 (R025)"""
    row = (await db.execute(
        select(UserInfo.account_age_days).where(UserInfo.user_id == user_id)
    )).first()
    return float(row.account_age_days) if row else 0.0


# ============================================================
# 订单维度特征 (8 个)
# ============================================================
async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """订单总金额"""
    return await _sum(OrderInfo, "total_amount", db, order_id=order_id)


async def _feat_order_passenger_count(db: AsyncSession, order_id: str) -> float:
    """乘客数 (订单冗余字段, 免 join)"""
    row = (await db.execute(
        select(OrderInfo.passenger_count).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.passenger_count) if row else 0.0


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否凌晨 1-5 点下单 (0 点突击下单)"""
    row = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 1 <= row.create_time.hour <= 5 else 0.0
    return 0.0


async def _feat_order_days_to_depart(db: AsyncSession, order_id: str) -> float:
    """下单距出发天数 (临期大额 / 突击下单信号)"""
    row = (await db.execute(
        select(OrderInfo.create_time, OrderInfo.depart_date).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time and row.depart_date:
        return max(float((row.depart_date - row.create_time.date()).days), 0)
    return 0.0


async def _feat_order_trip_days(db: AsyncSession, order_id: str) -> float:
    """行程天数 = 返回日 - 出发日"""
    row = (await db.execute(
        select(OrderInfo.depart_date, OrderInfo.return_date).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.depart_date and row.return_date:
        return float((row.return_date - row.depart_date).days)
    return 0.0


async def _feat_order_is_international(db: AsyncSession, order_id: str) -> float:
    """是否出境订单 (目的地国家不在国内集合)"""
    row = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.dest_country:
        return 1.0 if row.dest_country not in DOMESTIC_DESTS else 0.0
    return 0.0


async def _feat_order_same_flight_1h_count(db: AsyncSession, order_id: str) -> float:
    """同航班 1 小时窗口预订数 (含本单, 黄牛囤票核心信号 R008)"""
    flight = (await db.execute(
        select(BookingFlight.flight_no).where(BookingFlight.order_id == order_id)
    )).first()
    ts = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not flight or not ts or not ts.create_time:
        return 0.0
    stmt = (
        select(func.count())
        .select_from(BookingFlight)
        .join(OrderInfo, BookingFlight.order_id == OrderInfo.order_id)
        .where(
            BookingFlight.flight_no == flight.flight_no,
            func.abs(func.timestampdiff(text("SECOND"), OrderInfo.create_time, ts.create_time)) <= 3600,
        )
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_new_passenger_rate(db: AsyncSession, order_id: str) -> float:
    """新乘客占比: 本单乘客中从未在该用户历史订单出现过的比例 (乘客信息不一致 R018)"""
    user = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id)
    )).first()
    current = (await db.execute(
        select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
    )).scalars().all()
    if not current:
        return 0.0
    if not user:
        return 1.0
    other_ids = set((await db.execute(
        select(PassengerInfo.id_number)
        .join(OrderInfo, PassengerInfo.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == user.user_id, OrderInfo.order_id != order_id)
    )).scalars().all())
    new_count = sum(1 for p in current if p not in other_ids)
    return round(new_count / len(current), 4)


# ============================================================
# 地址维度特征 (3 个) — 旅游行业映射为"目的地/行程"维度
# ============================================================
async def _feat_addr_dest_country_count(db: AsyncSession, user_id: str) -> float:
    """历史不同目的地国家数 (旅行目的地多样性)"""
    stmt = select(func.count(func.distinct(OrderInfo.dest_country))).where(
        OrderInfo.user_id == user_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_international_order_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """出境订单占比"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    rows = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.user_id == user_id)
    )).scalars().all()
    intl = sum(1 for d in rows if d not in DOMESTIC_DESTS)
    return round(intl / total_orders, 4)


async def _feat_addr_current_dest_used_before(
    db: AsyncSession, user_id: str, order_id: str | None,
) -> float:
    """当前目的地是否用户去过的目的地 (0=新目的地, 1=去过)"""
    if not order_id:
        return 0.0
    dest = (await db.execute(
        select(OrderInfo.dest_country).where(OrderInfo.order_id == order_id)
    )).first()
    if not dest or not dest.dest_country:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.order_id != order_id,
            OrderInfo.dest_country == dest.dest_country,
        )
    )).scalar() or 0
    return 1.0 if cnt > 0 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================
async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征 (total_orders 预查复用给 3 个派生特征)"""
    total_orders = await _feat_user_total_orders(db, user_id)

    independent = {
        "user_orders_30d": _feat_user_orders_30d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_cancel_count": _feat_user_cancel_count,
        "user_refund_count": _feat_user_refund_count,
        "user_night_order_count": _feat_user_night_order_count,
        "user_same_flight_1h_count": _feat_user_same_flight_1h_count,
        "user_visa_apply_count": _feat_user_visa_apply_count,
        "user_visa_reject_count": _feat_user_visa_reject_count,
        "user_visa_multi_country_30d": _feat_user_visa_multi_country_30d,
        "user_account_age_days": _feat_user_account_age_days,
    }
    features = {name: await fn(db, user_id) for name, fn in independent.items()}
    features["user_total_orders"] = total_orders
    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(
        db, user_id, total_orders=total_orders)
    features["user_refund_rate"] = await _feat_user_refund_rate(
        db, user_id, total_orders=total_orders)
    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个订单维度特征. 无订单事件 (签证申请) 返回全 0, 保证 25 维对齐."""
    if not order_id:
        return {name: 0.0 for name in (
            "order_total_amount", "order_passenger_count", "order_is_night",
            "order_days_to_depart", "order_trip_days", "order_is_international",
            "order_same_flight_1h_count", "order_new_passenger_rate",
        )}
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_passenger_count": _feat_order_passenger_count,
        "order_is_night": _feat_order_is_night,
        "order_days_to_depart": _feat_order_days_to_depart,
        "order_trip_days": _feat_order_trip_days,
        "order_is_international": _feat_order_is_international,
        "order_same_flight_1h_count": _feat_order_same_flight_1h_count,
        "order_new_passenger_rate": _feat_order_new_passenger_rate,
    }
    return {name: await fn(db, order_id) for name, fn in feat_funcs.items()}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
    order_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个目的地维度特征 (旅游行业把"地址"族映射到"目的地/行程")."""
    total_orders = await _feat_user_total_orders(db, user_id)
    return {
        "addr_dest_country_count": await _feat_addr_dest_country_count(db, user_id),
        "addr_international_order_rate": await _feat_addr_international_order_rate(
            db, user_id, total_orders=total_orders),
        "addr_current_dest_used_before": await _feat_addr_current_dest_used_before(
            db, user_id, order_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回 (25 维)."""
    features = await compute_user_features(db, user_id)
    # 无订单事件 (签证申请) 也补全 order_* = 0, 保证 25 维对齐 (训练/推理特征顺序稳定)
    features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id, order_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 — 无需 DB
# 跑法: python -m app.engine.feature
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 (旅游行业) — 25 维特征名 + 字典派发表")
    print("=" * 60)

    user_feats = [
        ("user_total_orders",           "历史订单总数"),
        ("user_orders_30d",             "近 30 天订单数"),
        ("user_total_amount",           "历史消费总额"),
        ("user_avg_order_amount",       "平均订单金额"),
        ("user_max_order_amount",       "最大单笔订单金额"),
        ("user_cancel_count",           "已取消订单数"),
        ("user_refund_count",           "退改次数"),
        ("user_refund_rate",            "退改率"),
        ("user_night_order_count",      "凌晨 1-5 点下单数"),
        ("user_same_flight_1h_count",   "同航班 1 小时窗口最大预订数"),
        ("user_visa_apply_count",       "签证申请总数"),
        ("user_visa_reject_count",      "拒签次数"),
        ("user_visa_multi_country_30d", "30 天申请不同国家数"),
        ("user_account_age_days",       "注册时长(天)"),
    ]
    order_feats = [
        ("order_total_amount",          "订单金额"),
        ("order_passenger_count",       "乘客数"),
        ("order_is_night",              "是否凌晨下单"),
        ("order_days_to_depart",        "下单距出发天数"),
        ("order_trip_days",             "行程天数"),
        ("order_is_international",      "是否出境"),
        ("order_same_flight_1h_count",  "同航班 1 小时窗口预订数"),
        ("order_new_passenger_rate",    "新乘客占比"),
    ]
    addr_feats = [
        ("addr_dest_country_count",          "历史不同目的地国家数"),
        ("addr_international_order_rate",    "出境订单占比"),
        ("addr_current_dest_used_before",    "当前目的地是否去过"),
    ]
    total = 0
    for sec, feats in [("用户 (14)", user_feats), ("订单 (8)", order_feats), ("目的地 (3)", addr_feats)]:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<32} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 ml_model.py::FEATURE_COLUMNS 一一对应)")
