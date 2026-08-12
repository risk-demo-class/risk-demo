"""
特征工程模块 (物流行业版): 通过 ORM 查询业务数据, 计算 25 个风控特征.
【重要】25 维特征 key 名与 ml_model.py::FEATURE_COLUMNS 严格对齐 (user_* 14 + order_* 8 + addr_* 3)
物流语义映射:
  user_total_orders    → user_total_shipments (历史寄件总数)
  order_total_amount   → shipment_declared_value (运单申报总价值)
  addr_total_count     → user_address_count (地址总数)
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Shipment, ShipmentItem, Address, ComplaintRecord, CustomsDeclaration,
    ItemCategory,
)


async def _count(model, db: AsyncSession, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, col_name: str, db: AsyncSession, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (14 个, 前缀 user_* 与 FEATURE_COLUMNS 对齐)
# 语义映射: 订单→寄件, 退款→拒收, 售后→投诉
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """user_total_orders → 历史寄件总数 (sender_user_id)"""
    return await _count(Shipment, db, sender_user_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天寄件数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_user_id == user_id,
        Shipment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天寄件数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_user_id == user_id,
        Shipment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """user_total_amount → 历史累计申报价值 (寄件人维度)"""
    stmt = select(func.coalesce(func.sum(Shipment.declared_value), 0)).select_from(
        Shipment
    ).where(Shipment.sender_user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均每单申报价值"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最高单笔运单申报价值"""
    stmt = select(func.coalesce(func.max(Shipment.declared_value), 0)).select_from(
        Shipment
    ).where(Shipment.sender_user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """user_refund_count → 拒收总次数 (reject_count 累加, 拒收=到付场景的退款)"""
    stmt = select(func.coalesce(func.sum(Shipment.reject_count), 0)).select_from(
        Shipment
    ).where(Shipment.sender_user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_postsale_count(db: AsyncSession, user_id: str) -> float:
    """user_postsale_count → 投诉总次数 (售后=投诉)"""
    return await _count(ComplaintRecord, db, user_id=user_id)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """拒收率 = 拒收次数 / 总寄件数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    refund_count = await _feat_user_refund_count(db, user_id)
    return round(refund_count / total_orders, 4)


async def _feat_user_postsale_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """投诉率 = 投诉次数 / 总寄件数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    postsale_count = await _feat_user_postsale_count(db, user_id)
    return round(postsale_count / total_orders, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    """user_refund_amount → 涉及拒收的运单申报总价值 (对应电商的退款金额)"""
    stmt = select(func.coalesce(func.sum(Shipment.declared_value), 0)).select_from(
        Shipment
    ).where(
        Shipment.sender_user_id == user_id,
        Shipment.reject_count >= 1,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """user_cancel_count → 已取消运单数 (shipment_status='已取消')"""
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_user_id == user_id,
        Shipment.shipment_status == "已取消",
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """user_complaint_count → 被投诉次数 (作为寄件人, 收件方投诉)"""
    stmt = select(func.count()).select_from(ComplaintRecord).join(
        Shipment, ComplaintRecord.shipment_id == Shipment.shipment_id
    ).where(
        Shipment.sender_user_id == user_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    """user_address_count → 寄件地址数量 (用户维度的地址总数)"""
    return await _count(Address, db, user_id=user_id)


# ============================================================
# 运单维度特征 (8 个, 前缀 order_* 与 FEATURE_COLUMNS 对齐)
# 语义映射: order → shipment (运单)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """order_total_amount → 运单申报总价值 (declared_value)"""
    row = (await db.execute(
        select(Shipment.declared_value).where(Shipment.shipment_id == order_id)
    )).first()
    return float(row.declared_value) if row else 0.0


async def _feat_order_item_count(db: AsyncSession, order_id: str) -> float:
    """订单商品行数 → 运单物品明细行数"""
    return await _count(ShipmentItem, db, shipment_id=order_id)


async def _feat_order_sku_count(db: AsyncSession, order_id: str) -> float:
    """订单 SKU 总数 → 运单物品总件数 (quantity 累加)"""
    return await _sum(ShipmentItem, "quantity", db, shipment_id=order_id)


async def _feat_order_discount_amount(db: AsyncSession, order_id: str) -> float:
    """折扣总金额 → 运单保价金额 (insurance_amount, 作为"额外费用"对应折扣的负值)"""
    row = (await db.execute(
        select(Shipment.insurance_amount).where(Shipment.shipment_id == order_id)
    )).first()
    return float(row.insurance_amount) if row else 0.0


async def _feat_order_discount_rate(db: AsyncSession, order_id: str) -> float:
    """折扣率 → 保价率 = 保价金额 / 申报价值 (高保价=高风险信号)"""
    row = (await db.execute(
        select(Shipment.insurance_amount, Shipment.declared_value
               ).where(Shipment.shipment_id == order_id)
    )).first()
    if not row or float(row.declared_value) == 0:
        return 0.0
    return round(float(row.insurance_amount) / float(row.declared_value), 4)


async def _feat_order_pay_interval(db: AsyncSession, order_id: str) -> float:
    """下单到支付时间差 → 下单到揽收时间差(秒)"""
    row = (await db.execute(
        select(Shipment.create_time, Shipment.pick_up_time
               ).where(Shipment.shipment_id == order_id)
    )).first()
    if row and row.pick_up_time and row.create_time:
        return max(float((row.pick_up_time - row.create_time).total_seconds()), 0)
    return -1


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否夜间寄件 (0~6 点创建运单)"""
    row = (await db.execute(
        select(Shipment.create_time).where(Shipment.shipment_id == order_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour < 6 else 0.0
    return 0.0


async def _feat_order_category_count(db: AsyncSession, order_id: str) -> float:
    """订单商品类别数 → 运单物品分类数 (DISTINCT category_code)"""
    stmt = select(func.count(func.distinct(ShipmentItem.category_code))).select_from(
        ShipmentItem
    ).where(ShipmentItem.shipment_id == order_id)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 地址维度特征 (3 个, 前缀 addr_* 与 FEATURE_COLUMNS 对齐)
# ============================================================

async def _feat_addr_total_count(db: AsyncSession, user_id: str) -> float:
    """用户地址总数 (同 user_address_count, 保持 addr_ 前缀独立)"""
    return await _count(Address, db, user_id=user_id)


async def _feat_addr_province_count(db: AsyncSession, user_id: str) -> float:
    """不同省份数 (用户地址覆盖的省份)"""
    stmt = select(func.count(func.distinct(Address.province))).select_from(
        Address
    ).where(Address.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_is_new(
    db: AsyncSession, user_id: str, receive_id: str | None
) -> float:
    """addr_is_new → 收件地址是否新 (该 address_id 在用户寄件历史中使用次数 <= 1)"""
    if not receive_id:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(Shipment).where(
            Shipment.sender_user_id == user_id,
            Shipment.receiver_address_id == receive_id,
        )
    )).scalar() or 0
    return 1.0 if cnt <= 1 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征 (物流语义)."""
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


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个运单维度特征."""
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
    return {name: await func(db, order_id) for name, func in feat_funcs.items()}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个地址维度特征."""
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
    """一次性计算全部 25 维特征."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features


if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 (物流版) — 25 维特征语义映射")
    print("=" * 60)
    user_feats = [
        ("user_total_orders",     "历史寄件总数 (sender_user_id)"),
        ("user_orders_7d",        "近 7 天寄件数"),
        ("user_orders_30d",       "近 30 天寄件数"),
        ("user_total_amount",     "历史累计申报价值"),
        ("user_avg_order_amount", "平均每单申报价值"),
        ("user_max_order_amount", "最高单笔申报价值"),
        ("user_refund_count",     "拒收总次数 (reject_count 累加)"),
        ("user_postsale_count",   "投诉总次数"),
        ("user_refund_rate",      "拒收率"),
        ("user_postsale_rate",    "投诉率"),
        ("user_refund_amount",    "拒收涉及的申报总价值"),
        ("user_cancel_count",     "已取消运单数"),
        ("user_complaint_count",  "被投诉次数 (收件人投诉寄件人)"),
        ("user_address_count",    "寄件地址数量"),
    ]
    order_feats = [
        ("order_total_amount",    "运单申报价值 declared_value"),
        ("order_item_count",      "运单物品明细行数"),
        ("order_sku_count",       "运单物品总件数 (∑quantity)"),
        ("order_discount_amount", "保价金额 insurance_amount (高保价=风险)"),
        ("order_discount_rate",   "保价率 = 保价/申报价值"),
        ("order_pay_interval",    "下单到揽收时间差 (秒)"),
        ("order_is_night",        "夜间寄件 (0-6 点创建)"),
        ("order_category_count",  "运单物品分类数 (DISTINCT)"),
    ]
    addr_feats = [
        ("addr_total_count",      "用户地址总数"),
        ("addr_province_count",   "覆盖省份数"),
        ("addr_is_new",           "收件地址是否新 (使用次数<=1)"),
    ]
    all_groups = [("用户 (14)", user_feats), ("运单 (8)", order_feats), ("地址 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (与 ml_model.py::FEATURE_COLUMNS key 名 1:1 对齐)")
