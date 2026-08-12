"""
制造业风控系统 - 特征工程模块: 通过 ORM 查询业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx  = 经销商用户维度特征
  order_xxx = 订货/保修事件维度特征
  addr_xxx  = 区域维度特征 (制造业用"发货区域"替代电商"收货地址")

【行业约定】经销商用户 user_id 即业务账号, 与 dealer_info.dealer_id 一致.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CrossRegionReport,
    DealerInfo,
    OrderInfo,
    Product,
    WarrantyRecord,
)


# 通用 SQL 工具
async def _count(db: AsyncSession, model, **filters) -> float:
    """SELECT COUNT(*) FROM model WHERE filters."""
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(db: AsyncSession, model, col_name: str, **filters) -> float:
    """SELECT COALESCE(SUM(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 经销商用户维度特征 (13 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史订货单总数"""
    return await _count(db, OrderInfo, dealer_id=user_id)


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
    """历史订货总金额"""
    return await _sum(db, OrderInfo, "total_amount", dealer_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均订货金额 = 总金额 / 单数. total_orders 预传可避免 batch 重复查 SQL."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔订货金额"""
    stmt = select(func.coalesce(func.max(OrderInfo.total_amount), 0)).where(
        OrderInfo.dealer_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_warranty_count(db: AsyncSession, user_id: str) -> float:
    """关联设备保修总次数 (warranty → order → dealer)"""
    stmt = select(func.count()).select_from(WarrantyRecord).join(
        OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id
    ).where(OrderInfo.dealer_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_repair_cost_total(db: AsyncSession, user_id: str) -> float:
    """累计维修费用"""
    stmt = select(func.coalesce(func.sum(WarrantyRecord.repair_cost), 0)).select_from(
        WarrantyRecord
    ).join(OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id).where(
        OrderInfo.dealer_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_repair_cost_avg(
    db: AsyncSession, user_id: str, warranty_count: float | None = None,
) -> float:
    """平均维修费用 = 累计维修费 / 保修次数"""
    if warranty_count is None:
        warranty_count = await _feat_user_warranty_count(db, user_id)
    if warranty_count == 0:
        return 0
    total = await _feat_user_repair_cost_total(db, user_id)
    return round(total / warranty_count, 2)


async def _feat_user_warranty_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
    warranty_count: float | None = None,
) -> float:
    """保修率 = 保修次数 / 订货单数"""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    if warranty_count is None:
        warranty_count = await _feat_user_warranty_count(db, user_id)
    return round(warranty_count / total_orders, 4)


async def _feat_user_out_warranty_count(db: AsyncSession, user_id: str) -> float:
    """保修期外报修次数 (报修日期 > 订单日期 + 产品保修月数)"""
    stmt = select(func.count()).select_from(WarrantyRecord).join(
        OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id
    ).join(Product, OrderInfo.product_id == Product.product_id).where(
        OrderInfo.dealer_id == user_id,
        text("DATE_ADD(order_info.create_time, INTERVAL product.warranty_months MONTH) < warranty_record.issue_date"),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cross_report_count(db: AsyncSession, user_id: str) -> float:
    """被跨区串货举报次数"""
    return await _count(db, CrossRegionReport, dealer_id=user_id)


async def _feat_user_contract_age_days(db: AsyncSession, user_id: str) -> float:
    """经销商签约时长(天): 从合同开始到现在的天数, 无档案返回 0"""
    row = (await db.execute(
        select(DealerInfo.contract_start).where(DealerInfo.dealer_id == user_id)
    )).first()
    if row and row.contract_start:
        return max(float((datetime.now() - row.contract_start).total_seconds() / 86400), 0)
    return 0.0


# ============================================================
# 订货/保修事件维度特征 (9 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """订单总金额"""
    return await _sum(db, OrderInfo, "total_amount", order_id=order_id)


async def _feat_order_quantity(db: AsyncSession, order_id: str) -> float:
    """订货数量(台)"""
    return await _sum(db, OrderInfo, "quantity", order_id=order_id)


async def _feat_order_unit_price(db: AsyncSession, order_id: str) -> float:
    """成交单价 = 总金额 / 数量, 无数据返回 0"""
    total = await _feat_order_total_amount(db, order_id)
    qty = await _feat_order_quantity(db, order_id)
    return round(total / qty, 2) if qty > 0 else 0.0


async def _feat_order_is_night(db: AsyncSession, order_id: str) -> float:
    """是否夜间下单 (0~6 点)"""
    row = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour < 6 else 0.0
    return 0.0


async def _feat_order_is_cross_region(db: AsyncSession, order_id: str) -> float:
    """是否跨区发货: 订单收货区域 != 经销商授权区域"""
    row = (await db.execute(
        select(OrderInfo.ship_to_region, DealerInfo.region)
        .select_from(OrderInfo)
        .join(DealerInfo, OrderInfo.dealer_id == DealerInfo.dealer_id)
        .where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.ship_to_region and row.region:
        return 1.0 if row.ship_to_region != row.region else 0.0
    return 0.0


async def _feat_order_contract_expired(db: AsyncSession, order_id: str) -> float:
    """经销商合同是否已过期 (1=过期)"""
    row = (await db.execute(
        select(DealerInfo.contract_end)
        .select_from(OrderInfo)
        .join(DealerInfo, OrderInfo.dealer_id == DealerInfo.dealer_id)
        .where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.contract_end:
        return 1.0 if row.contract_end < datetime.now() else 0.0
    return 0.0


async def _count_warranty_window(
    db: AsyncSession, order_id: str, product_sn: str | None, days: int,
) -> float:
    """近 N 天同设备保修次数: 有 SN 按 SN 统计, 否则按订单统计"""
    since = datetime.now() - timedelta(days=days)
    stmt = select(func.count()).select_from(WarrantyRecord).where(
        WarrantyRecord.issue_date >= since,
    )
    if product_sn:
        stmt = stmt.where(WarrantyRecord.product_sn == product_sn)
    else:
        stmt = stmt.where(WarrantyRecord.order_id == order_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_warranty_30d(
    db: AsyncSession, order_id: str, product_sn: str | None,
) -> float:
    """近 30 天同设备保修次数 (保修期外高频保修 R002 用)"""
    return await _count_warranty_window(db, order_id, product_sn, 30)


async def _feat_order_warranty_90d(
    db: AsyncSession, order_id: str, product_sn: str | None,
) -> float:
    """近 90 天同设备保修次数 (套保嫌疑 R008 用)"""
    return await _count_warranty_window(db, order_id, product_sn, 90)


async def _feat_order_repair_cost_ratio(db: AsyncSession, order_id: str) -> float:
    """维修费用/MSRP 占比: 取该订单最大单次维修费 / 产品官方建议零售价"""
    row = (await db.execute(
        select(
            func.max(WarrantyRecord.repair_cost),
            Product.msrp,
        )
        .select_from(WarrantyRecord)
        .join(OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id)
        .join(Product, OrderInfo.product_id == Product.product_id)
        .where(OrderInfo.order_id == order_id)
        .group_by(Product.msrp)
    )).first()
    if row and row.msrp and float(row.msrp) > 0:
        return round(float(row[0] or 0) / float(row.msrp), 4)
    return 0.0


async def _feat_order_cross_report_count(db: AsyncSession, order_id: str) -> float:
    """同一订单被跨区串货举报次数 (R001 任务书口径: 同一订单被举报>=2次)"""
    return await _count(db, CrossRegionReport, order_id=order_id)


# ============================================================
# 区域维度特征 (3 个, 制造业用"发货区域"替代"收货地址")
# ============================================================

async def _feat_addr_ship_region_count(db: AsyncSession, user_id: str) -> float:
    """经销商历史发货区域数 (DISTINCT ship_to_region)"""
    stmt = select(func.count(func.distinct(OrderInfo.ship_to_region))).select_from(
        OrderInfo
    ).where(OrderInfo.dealer_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_dealer_region_count(db: AsyncSession, user_id: str) -> float:
    """经销商授权区域数 (DISTINCT dealer_info.region, 多经销档案时 >1)"""
    stmt = select(func.count(func.distinct(DealerInfo.region))).select_from(
        DealerInfo
    ).where(DealerInfo.dealer_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_ship_is_new(
    db: AsyncSession, user_id: str, order_id: str | None,
) -> float:
    """本次发货区域是否该经销商首次使用 (1=新区域)"""
    if not order_id:
        return 0.0
    row = (await db.execute(
        select(OrderInfo.ship_to_region).where(OrderInfo.order_id == order_id)
    )).first()
    if not row or not row.ship_to_region:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.dealer_id == user_id,
            OrderInfo.ship_to_region == row.ship_to_region,
            OrderInfo.order_id != order_id,
        )
    )).scalar() or 0
    return 1.0 if cnt <= 0 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 13 个经销商用户维度特征."""
    total_orders = await _feat_user_total_orders(db, user_id)
    warranty_count = await _feat_user_warranty_count(db, user_id)

    independent_features = {
        "user_orders_30d": _feat_user_orders_30d,
        "user_orders_7d": _feat_user_orders_7d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_repair_cost_total": _feat_user_repair_cost_total,
        "user_out_warranty_count": _feat_user_out_warranty_count,
        "user_cross_report_count": _feat_user_cross_report_count,
        "user_contract_age_days": _feat_user_contract_age_days,
    }
    features = {name: await func(db, user_id) for name, func in independent_features.items()}
    features["user_total_orders"] = total_orders
    features["user_warranty_count"] = warranty_count

    # 派生特征: 传预查值避免重复 SQL
    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(
        db, user_id, total_orders=total_orders,
    )
    features["user_warranty_rate"] = await _feat_user_warranty_rate(
        db, user_id, total_orders=total_orders, warranty_count=warranty_count,
    )
    return features


async def compute_order_features(
    db: AsyncSession,
    order_id: str,
    product_sn: str | None = None,
) -> dict[str, float]:
    """计算 9 个订货/保修事件维度特征."""
    return {
        "order_total_amount": await _feat_order_total_amount(db, order_id),
        "order_quantity": await _feat_order_quantity(db, order_id),
        "order_unit_price": await _feat_order_unit_price(db, order_id),
        "order_is_night": await _feat_order_is_night(db, order_id),
        "order_is_cross_region": await _feat_order_is_cross_region(db, order_id),
        "order_contract_expired": await _feat_order_contract_expired(db, order_id),
        "order_warranty_30d": await _feat_order_warranty_30d(db, order_id, product_sn),
        "order_warranty_90d": await _feat_order_warranty_90d(db, order_id, product_sn),
        "order_repair_cost_ratio": await _feat_order_repair_cost_ratio(db, order_id),
        "order_cross_report_count": await _feat_order_cross_report_count(db, order_id),
    }


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个区域维度特征."""
    return {
        "addr_ship_region_count": await _feat_addr_ship_region_count(db, user_id),
        "addr_dealer_region_count": await _feat_addr_dealer_region_count(db, user_id),
        "addr_ship_is_new": await _feat_addr_ship_is_new(db, user_id, order_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
    product_sn: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 25 个特征并合并返回.

    receive_id 仅保留兼容签名 (电商地址概念, 制造业不用).
    """
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id, product_sn))
    features.update(await compute_address_features(db, user_id, order_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("制造业特征工程 — 25 维特征名 + 字典派发表")
    print("=" * 60)

    user_feats = [
        ("user_total_orders",        "历史订货单总数"),
        ("user_orders_7d",           "近 7 天订货单数"),
        ("user_orders_30d",          "近 30 天订货单数"),
        ("user_total_amount",        "历史订货总金额"),
        ("user_avg_order_amount",    "平均订货金额"),
        ("user_max_order_amount",    "最大单笔订货金额"),
        ("user_warranty_count",      "设备保修次数"),
        ("user_warranty_rate",       "保修率(保修/订货)"),
        ("user_repair_cost_total",   "累计维修费用"),
        ("user_out_warranty_count",  "保修期外报修次数"),
        ("user_cross_report_count",  "被跨区串货举报次数"),
        ("user_contract_age_days",   "经销商签约时长(天)"),
    ]
    order_feats = [
        ("order_total_amount",    "订单总金额"),
        ("order_quantity",        "订货数量(台)"),
        ("order_unit_price",      "成交单价"),
        ("order_is_night",        "是否夜间下单 (0-6 点)"),
        ("order_is_cross_region", "是否跨区发货 (0/1)"),
        ("order_contract_expired","经销商合同是否过期 (0/1)"),
        ("order_warranty_30d",    "近 30 天同设备保修次数"),
        ("order_warranty_90d",    "近 90 天同设备保修次数"),
        ("order_repair_cost_ratio","单次维修费用/MSRP"),
        ("order_cross_report_count","同一订单被串货举报次数"),
    ]
    addr_feats = [
        ("addr_ship_region_count",   "经销商历史发货区域数"),
        ("addr_dealer_region_count", "经销商授权区域数"),
        ("addr_ship_is_new",         "本次发货区域是否首次 (0/1)"),
    ]
    all_groups = [("经销商用户 (12)", user_feats), ("订货/保修事件 (10)", order_feats), ("区域 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
