"""
特征工程模块: 通过 ORM 查询物流业务数据, 计算 25 个风控特征

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户维度特征 (寄件人)
  order_xxx  = 运单维度特征
  addr_xxx   = 地址维度特征 (目的地址)

物流映射说明 (保持 25 个特征名不变, 规则引擎 / XGBoost 兼容):
  user_refund_*   -> 已取消运单 (取消率)
  user_postsale_* -> 运单投诉
  order_*         -> 运单 (申报价值 / 物品明细)
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Address,
    Shipment,
    ShipmentComplaint,
    ShipmentItem,
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


async def _max(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(MAX(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.max(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (14 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史运单总数 (寄件)"""
    return await _count(Shipment, db, sender_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天运单数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id,
        Shipment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天运单数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id,
        Shipment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史申报价值总额"""
    return await _sum(Shipment, "declared_value", db, sender_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均申报价值 = 总额 / 运单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """单笔最高申报价值"""
    return await _max(Shipment, "declared_value", db, sender_id=user_id)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """取消运单总次数 (status='已取消')"""
    return await _count(Shipment, db, sender_id=user_id, status="已取消")


async def _feat_user_postsale_count(db: AsyncSession, user_id: str) -> float:
    """投诉总次数 (运单投诉记录)"""
    return await _count(ShipmentComplaint, db, user_id=user_id)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """取消率 = 取消运单数 / 总运单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    refund_count = await _feat_user_refund_count(db, user_id)
    return round(refund_count / total_orders, 4)


async def _feat_user_postsale_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """投诉率 = 投诉次数 / 总运单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    postsale_count = await _feat_user_postsale_count(db, user_id)
    return round(postsale_count / total_orders, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    """取消运单申报价值总额"""
    return await _sum(Shipment, "declared_value", db, sender_id=user_id, status="已取消")


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """取消运单次数 (status='已取消')"""
    return await _count(Shipment, db, sender_id=user_id, status="已取消")


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """投诉次数 (运单投诉记录表)"""
    return await _count(ShipmentComplaint, db, user_id=user_id)


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    """收货地址数量 (用户所有运单的目的地址去重)"""
    stmt = select(func.count(func.distinct(Shipment.dest_address_id))).select_from(
        Shipment
    ).where(Shipment.sender_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 运单维度特征 (8 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, shipment_id: str) -> float:
    """运单申报价值"""
    return await _sum(Shipment, "declared_value", db, shipment_id=shipment_id)


async def _feat_order_item_count(db: AsyncSession, shipment_id: str) -> float:
    """运单物品行数"""
    return await _count(ShipmentItem, db, shipment_id=shipment_id)


async def _feat_order_sku_count(db: AsyncSession, shipment_id: str) -> float:
    """运单物品总数量 (累加 quantity)"""
    return await _sum(ShipmentItem, "quantity", db, shipment_id=shipment_id)


async def _feat_order_discount_amount(db: AsyncSession, shipment_id: str) -> float:
    """物流行业无折扣概念, 恒为 0"""
    return 0.0


async def _feat_order_discount_rate(db: AsyncSession, shipment_id: str) -> float:
    """物流行业无折扣概念, 恒为 0"""
    return 0.0


async def _feat_order_pay_interval(db: AsyncSession, shipment_id: str) -> float:
    """物流行业无支付环节, 恒为 -1"""
    return -1.0


async def _feat_order_is_night(db: AsyncSession, shipment_id: str) -> float:
    """是否深夜下单 (运单创建时间 0~6 点)"""
    row = (await db.execute(
        select(Shipment.create_time).where(Shipment.shipment_id == shipment_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour < 6 else 0.0
    return 0.0


async def _feat_order_category_count(db: AsyncSession, shipment_id: str) -> float:
    """运单物品类别数 (DISTINCT item_category)"""
    stmt = select(func.count(func.distinct(ShipmentItem.item_category))).select_from(
        ShipmentItem
    ).where(ShipmentItem.shipment_id == shipment_id)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 地址维度特征 (3 个)
# ============================================================

async def _feat_addr_total_count(db: AsyncSession, user_id: str) -> float:
    """用户收货地址总数 (目的地址去重)"""
    return await _feat_user_address_count(db, user_id)


async def _feat_addr_province_count(db: AsyncSession, user_id: str) -> float:
    """用户收货地址覆盖省份数"""
    stmt = (
        select(func.count(func.distinct(Address.province)))
        .select_from(Shipment)
        .join(Address, Address.address_id == Shipment.dest_address_id)
        .where(Shipment.sender_id == user_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_is_new(
    db: AsyncSession, user_id: str, receive_id: str | None
) -> float:
    """是否新地址 (该用户使用此目的地址的次数 <= 1)"""
    if not receive_id:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(Shipment).where(
            Shipment.sender_id == user_id,
            Shipment.dest_address_id == receive_id,
        )
    )).scalar() or 0
    return 1.0 if cnt <= 1 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征"""
    total_orders = await _feat_user_total_orders(db, user_id)

    independent_features = {
        "user_orders_30d": _feat_user_orders_30d,
        "user_orders_7d": _feat_user_orders_7d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_refund_count": _feat_user_refund_count,
        "user_postsale_count": _feat_user_postsale_count,
        "user_refund_amount": _feat_user_refund_amount,
        "user_cancel_count": _feat_user_cancel_count,
        "user_complaint_count": _feat_user_complaint_count,
        "user_address_count": _feat_user_address_count,
    }
    features = {name: await func(db, user_id) for name, func in independent_features.items()}
    features["user_total_orders"] = total_orders

    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(db, user_id, total_orders=total_orders)
    features["user_refund_rate"] = await _feat_user_refund_rate(db, user_id, total_orders=total_orders)
    features["user_postsale_rate"] = await _feat_user_postsale_rate(db, user_id, total_orders=total_orders)

    return features


async def compute_order_features(db: AsyncSession, shipment_id: str) -> dict[str, float]:
    """计算 8 个运单维度特征"""
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_item_count": _feat_order_item_count,
        "order_sku_count": _feat_order_sku_count,
        "order_discount_amount": _feat_order_discount_amount,
        "order_discount_rate": _feat_order_discount_rate,
        "order_pay_interval_sec": _feat_order_pay_interval,
        "order_is_night": _feat_order_is_night,
        "order_category_count": _feat_order_category_count,
    }
    return {name: await func(db, shipment_id) for name, func in feat_funcs.items()}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个地址维度特征"""
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
    """一次性计算全部特征并合并返回"""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 (无 DB 依赖)
# 运行方式: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 - 25 维特征名 + 字典派发表 (物流版)")
    print("=" * 60)

    user_feats = [
        ("user_total_orders",     "历史运单总数"),
        ("user_orders_7d",        "近 7 天运单数"),
        ("user_orders_30d",       "近 30 天运单数"),
        ("user_total_amount",     "历史申报价值总额"),
        ("user_avg_order_amount", "平均申报价值"),
        ("user_max_order_amount", "单笔最高申报价值"),
        ("user_refund_count",     "取消运单总次数"),
        ("user_refund_rate",      "取消率"),
        ("user_refund_amount",    "取消运单申报价值总额"),
        ("user_postsale_count",   "投诉总次数"),
        ("user_postsale_rate",    "投诉率"),
        ("user_cancel_count",     "取消运单次数"),
        ("user_complaint_count",  "投诉次数"),
        ("user_address_count",    "收货地址数量"),
    ]
    order_feats = [
        ("order_total_amount",    "运单申报价值"),
        ("order_item_count",      "物品行数"),
        ("order_sku_count",       "物品总数量"),
        ("order_discount_amount", "折扣金额 (物流恒 0)"),
        ("order_discount_rate",   "折扣率 (物流恒 0)"),
        ("order_pay_interval",    "寄件到签收间隔 (物流恒 -1)"),
        ("order_is_night",        "是否深夜寄件 (0-6 点)"),
        ("order_category_count",  "物品类别数"),
    ]
    addr_feats = [
        ("addr_total_count",      "用户收货地址总数"),
        ("addr_province_count",   "不同省份数"),
        ("addr_is_new",           "本次地址是否新 (0/1)"),
    ]
    all_groups = [("用户 (14)", user_feats), ("运单 (8)", order_feats), ("地址 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (与 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
    print("=" * 60)
