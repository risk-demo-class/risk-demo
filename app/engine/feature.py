"""
制造业特征工程模块: 通过 ORM 查询业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户(经销商)维度特征
  order_xxx  = 订单(订货单)维度特征
  addr_xxx   = 区域维度特征 (制造业没有收货地址, 用"发货区域"替代)

【跟电商版的差异】
  - 用户特征: 从 C 端"退款/投诉"换成 B 端"保修率/被举报串货/合同资质"
  - 订单特征: 从"SKU/折扣/支付"换成"MSRP 折扣比/跨区匹配/SN 套保/维修费用比"
  - 地址特征: 从"收货地址"换成"发货区域覆盖/跨区订单/新区域"
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrossRegionReport, DealerInfo, OrderInfo, Product, WarrantyRecord


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


async def _get_order_row(db: AsyncSession, order_id: str):
    """取订单行 (含产品 ID/单价/区域/状态/时间)."""
    if not order_id:
        return None
    return (await db.execute(
        select(OrderInfo).where(OrderInfo.order_id == order_id).limit(1)
    )).scalar_one_or_none()


async def _get_latest_warranty_sn(db: AsyncSession, order_id: str) -> str | None:
    """取该订单最近一次保修/维修工单的 SN (套保特征按 SN 聚合的基础)."""
    if not order_id:
        return None
    row = (await db.execute(
        select(WarrantyRecord.product_sn)
        .where(WarrantyRecord.order_id == order_id)
        .order_by(WarrantyRecord.issue_date.desc())
        .limit(1)
    )).first()
    return row.product_sn if row else None


async def _get_latest_warranty_cost(db: AsyncSession, order_id: str) -> float | None:
    """取该订单最近一次保修/维修工单的费用."""
    if not order_id:
        return None
    row = (await db.execute(
        select(WarrantyRecord.repair_cost)
        .where(WarrantyRecord.order_id == order_id)
        .order_by(WarrantyRecord.issue_date.desc())
        .limit(1)
    )).first()
    return float(row.repair_cost) if row and row.repair_cost is not None else None


# ============================================================
# 用户(经销商)维度特征 (12 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史订货/采购单总数"""
    return await _count(OrderInfo, db, dealer_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天订货单数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.dealer_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天订货单数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.dealer_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史订货总额"""
    return await _sum(OrderInfo, "total_amount", db, dealer_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均订货金额 = 总金额 / 订单数."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔订货金额"""
    stmt = select(func.coalesce(func.max(OrderInfo.total_amount), 0)).select_from(
        OrderInfo
    ).where(OrderInfo.dealer_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_warranty_count(db: AsyncSession, user_id: str) -> float:
    """历史保修+维修总次数 (保修率分子)"""
    stmt = select(func.count()).select_from(WarrantyRecord).join(
        OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id
    ).where(OrderInfo.dealer_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_repair_count(db: AsyncSession, user_id: str) -> float:
    """历史维修次数 (issue_type='维修', 套保主体)"""
    stmt = select(func.count()).select_from(WarrantyRecord).join(
        OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id
    ).where(
        OrderInfo.dealer_id == user_id,
        WarrantyRecord.issue_type == "维修",
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_warranty_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """保修率 = 保修+维修次数 / 总订货数."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    warranty_count = await _feat_user_warranty_count(db, user_id)
    return round(warranty_count / total_orders, 4)


async def _feat_user_dealer_contract_expired(db: AsyncSession, user_id: str) -> float:
    """经销商合同是否已过期 (0/1)"""
    row = (await db.execute(
        select(DealerInfo.contract_end).where(DealerInfo.dealer_id == user_id).limit(1)
    )).first()
    if not row or not row.contract_end:
        return 0.0
    return 1.0 if row.contract_end < datetime.now() else 0.0


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """取消订货次数"""
    return await _count(OrderInfo, db, dealer_id=user_id, order_status="已取消")


async def _feat_user_report_count(db: AsyncSession, user_id: str) -> float:
    """被举报串货次数"""
    return await _count(CrossRegionReport, db, dealer_id=user_id)


# ============================================================
# 订单(订货单)维度特征 (10 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    row = await _get_order_row(db, order_id)
    return float(row.total_amount) if row and row.total_amount is not None else 0


async def _feat_order_quantity(db: AsyncSession, order_id: str) -> float:
    row = await _get_order_row(db, order_id)
    return float(row.quantity or 0) if row else 0


async def _feat_order_unit_price(db: AsyncSession, order_id: str) -> float:
    row = await _get_order_row(db, order_id)
    return float(row.unit_price or 0) if row else 0


async def _feat_order_msrp_ratio(db: AsyncSession, order_id: str) -> float:
    """成交价 / MSRP 折扣比 (<=0.5 疑似低价串货)"""
    row = await _get_order_row(db, order_id)
    if not row or not row.unit_price:
        return 0
    msrp = (await db.execute(
        select(Product.msrp).where(Product.product_id == row.product_id).limit(1)
    )).scalar_one_or_none()
    if not msrp:
        return 0
    return round(float(row.unit_price) / float(msrp), 4)


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否夜间下单 (0~6 点)"""
    row = await _get_order_row(db, order_id)
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour < 6 else 0.0
    return 0.0


async def _feat_order_ship_region_match(db: AsyncSession, order_id: str) -> float:
    """是否发货到经销商授权区域 (0=跨区, 1=本区)"""
    row = await _get_order_row(db, order_id)
    if not row:
        return 0.0
    dealer_region = (await db.execute(
        select(DealerInfo.region).where(DealerInfo.dealer_id == row.dealer_id).limit(1)
    )).scalar_one_or_none()
    if not dealer_region:
        return 0.0
    return 1.0 if row.ship_to_region == dealer_region else 0.0


async def _feat_order_sn_repair_count_90d(db: AsyncSession, order_id: str) -> float:
    """该订单设备 SN 近 90 天保修+维修次数 (套保识别核心特征)"""
    sn = await _get_latest_warranty_sn(db, order_id)
    if not sn:
        return 0
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.count()).select_from(WarrantyRecord).where(
        WarrantyRecord.product_sn == sn,
        WarrantyRecord.issue_date >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_report_count(db: AsyncSession, order_id: str) -> float:
    """该订单被举报串货次数 (R001 核心特征)"""
    return await _count(CrossRegionReport, db, order_id=order_id)


async def _feat_order_repair_cost_ratio(db: AsyncSession, order_id: str) -> float:
    """最近一次维修费用 / 产品 MSRP (R018 核心特征)"""
    cost = await _get_latest_warranty_cost(db, order_id)
    row = await _get_order_row(db, order_id)
    if cost is None or not row:
        return 0
    msrp = (await db.execute(
        select(Product.msrp).where(Product.product_id == row.product_id).limit(1)
    )).scalar_one_or_none()
    if not msrp:
        return 0
    return round(cost / float(msrp), 4)


async def _feat_order_is_out_of_warranty(db: AsyncSession, order_id: str) -> float:
    """产品是否已过保修期 (0/1): 订单时间 + 保修月数 < 当前时间"""
    row = await _get_order_row(db, order_id)
    if not row or not row.create_time:
        return 0.0
    warranty_months = (await db.execute(
        select(Product.warranty_months).where(Product.product_id == row.product_id).limit(1)
    )).scalar_one_or_none()
    if not warranty_months:
        return 0.0
    warranty_end = row.create_time + timedelta(days=30 * int(warranty_months))
    return 1.0 if warranty_end < datetime.now() else 0.0


# ============================================================
# 区域维度特征 (3 个, 制造业以"发货区域"替代"收货地址")
# ============================================================

async def _feat_addr_region_total(db: AsyncSession, user_id: str) -> float:
    """经销商历史发货区域数 (DISTINCT ship_to_region)"""
    stmt = select(func.count(func.distinct(OrderInfo.ship_to_region))).select_from(
        OrderInfo
    ).where(OrderInfo.dealer_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_region_cross_count(
    db: AsyncSession, user_id: str, dealer_region: str,
) -> float:
    """跨区订单数 (ship_to_region != dealer_region)"""
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.dealer_id == user_id,
        OrderInfo.ship_to_region != dealer_region,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_is_new_region(db: AsyncSession, user_id: str, order_id: str | None) -> float:
    """本次订单是否首次发货到该区域 (0/1)"""
    if not order_id:
        return 0.0
    row = await _get_order_row(db, order_id)
    if not row or not row.ship_to_region:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.dealer_id == user_id,
            OrderInfo.ship_to_region == row.ship_to_region,
        )
    )).scalar() or 0
    return 1.0 if cnt <= 1 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 12 个用户(经销商)维度特征."""
    total_orders = await _feat_user_total_orders(db, user_id)

    independent_features = {
        "user_orders_30d": _feat_user_orders_30d,
        "user_orders_7d": _feat_user_orders_7d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_warranty_count": _feat_user_warranty_count,
        "user_repair_count": _feat_user_repair_count,
        "user_dealer_contract_expired": _feat_user_dealer_contract_expired,
        "user_cancel_count": _feat_user_cancel_count,
        "user_report_count": _feat_user_report_count,
    }
    features = {name: await func(db, user_id) for name, func in independent_features.items()}
    features["user_total_orders"] = total_orders
    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(
        db, user_id, total_orders=total_orders,
    )
    features["user_warranty_rate"] = await _feat_user_warranty_rate(
        db, user_id, total_orders=total_orders,
    )
    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 10 个订单维度特征."""
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_quantity": _feat_order_quantity,
        "order_unit_price": _feat_order_unit_price,
        "order_msrp_ratio": _feat_order_msrp_ratio,
        "order_is_night": _feat_order_is_night,
        "order_ship_region_match": _feat_order_ship_region_match,
        "order_sn_repair_count_90d": _feat_order_sn_repair_count_90d,
        "order_report_count": _feat_order_report_count,
        "order_repair_cost_ratio": _feat_order_repair_cost_ratio,
        "order_is_out_of_warranty": _feat_order_is_out_of_warranty,
    }
    return {name: await func(db, order_id) for name, func in feat_funcs.items()}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个区域维度特征 (order_id 用于判定'本次是否新区域')."""
    dealer_region = (await db.execute(
        select(DealerInfo.region).where(DealerInfo.dealer_id == user_id).limit(1)
    )).scalar_one_or_none()
    cross_count = (
        await _feat_addr_region_cross_count(db, user_id, dealer_region)
        if dealer_region else 0.0
    )
    return {
        "addr_region_total": await _feat_addr_region_total(db, user_id),
        "addr_region_cross_count": cross_count,
        "addr_is_new_region": await _feat_addr_is_new_region(db, user_id, order_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, order_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 制造业 25 维特征名 + 分类")
    print("=" * 60)

    user_feats = [
        ("user_total_orders", "历史订货单总数"),
        ("user_orders_30d", "近 30 天订货单数"),
        ("user_orders_7d", "近 7 天订货单数"),
        ("user_total_amount", "历史订货总额"),
        ("user_avg_order_amount", "平均订货金额"),
        ("user_max_order_amount", "最大单笔订货金额"),
        ("user_warranty_count", "保修+维修总次数"),
        ("user_repair_count", "维修次数"),
        ("user_warranty_rate", "保修率"),
        ("user_dealer_contract_expired", "经销合同是否过期"),
        ("user_cancel_count", "取消订货次数"),
        ("user_report_count", "被举报串货次数"),
    ]
    order_feats = [
        ("order_total_amount", "订单总额"),
        ("order_quantity", "订购数量"),
        ("order_unit_price", "成交单价"),
        ("order_msrp_ratio", "成交价/MSRP 折扣比"),
        ("order_is_night", "是否夜间下单"),
        ("order_ship_region_match", "是否发货到授权区域"),
        ("order_sn_repair_count_90d", "SN 近 90 天保修+维修次数"),
        ("order_report_count", "订单被举报串货次数"),
        ("order_repair_cost_ratio", "最近维修费/MSRP"),
        ("order_is_out_of_warranty", "是否已过保修期"),
    ]
    addr_feats = [
        ("addr_region_total", "历史发货区域数"),
        ("addr_region_cross_count", "跨区订单数"),
        ("addr_is_new_region", "本次是否新发货区域"),
    ]
    all_groups = [("用户 (12)", user_feats), ("订单 (10)", order_feats), ("区域 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<32} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
