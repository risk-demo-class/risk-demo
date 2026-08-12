"""
特征工程模块: 通过 ORM 查询业务数据, 计算 26 个制造业风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  dealer_xxx    = 经销商维度特征
  order_xxx     = 订单(订货)维度特征
  product_xxx   = 产品维度特征
  warranty_xxx  = 保修/维修维度特征

业务边界: 经销商订货 / 设备保修 / 采购订单 / 售后维修
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BlacklistExtra,
    CrossRegionReport,
    DealerInfo,
    OrderInfo,
    Product,
    RiskBlacklist,
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


def _months_between(d1: datetime, d2: datetime) -> float:
    """两个日期相隔的月数 (d1 < d2 为正)."""
    return (d2 - d1).days / 30.0


# ============================================================
# 经销商维度特征 (12 个)
# ============================================================

async def _feat_dealer_total_orders(db: AsyncSession, dealer_id: str) -> float:
    """历史订货总单数"""
    return await _count(db, OrderInfo, dealer_id=dealer_id)


async def _feat_dealer_orders_30d(db: AsyncSession, dealer_id: str) -> float:
    """近 30 天订货数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.dealer_id == dealer_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dealer_orders_7d(db: AsyncSession, dealer_id: str) -> float:
    """近 7 天订货数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.dealer_id == dealer_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dealer_total_amount(db: AsyncSession, dealer_id: str) -> float:
    """历史订货总金额"""
    return await _sum(db, OrderInfo, "total_amount", dealer_id=dealer_id)


async def _feat_dealer_avg_order_amount(
    db: AsyncSession, dealer_id: str, total_orders: float | None = None,
) -> float:
    """平均订货金额 = 总金额 / 订货单数. total_orders 预传可避免重复查 SQL."""
    if total_orders is None:
        total_orders = await _feat_dealer_total_orders(db, dealer_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_dealer_total_amount(db, dealer_id)
    return round(total_amount / total_orders, 2)


async def _feat_dealer_max_order_amount(db: AsyncSession, dealer_id: str) -> float:
    """最大单笔订货金额"""
    stmt = select(func.coalesce(func.max(OrderInfo.total_amount), 0)).where(
        OrderInfo.dealer_id == dealer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dealer_contract_days(db: AsyncSession, dealer_id: str) -> float:
    """已签约天数 (合同开始到现在), 无合同返回 0"""
    row = (await db.execute(
        select(DealerInfo.contract_start).where(DealerInfo.dealer_id == dealer_id)
    )).first()
    if row and row.contract_start:
        return max(float((datetime.now() - row.contract_start).days), 0)
    return 0


async def _feat_dealer_contract_expired(db: AsyncSession, dealer_id: str) -> float:
    """合同是否已过期 (0/1): 合同结束时间 < 现在"""
    row = (await db.execute(
        select(DealerInfo.contract_end).where(DealerInfo.dealer_id == dealer_id)
    )).first()
    if row and row.contract_end:
        return 1.0 if row.contract_end < datetime.now() else 0.0
    return 0.0


async def _feat_dealer_warranty_count(db: AsyncSession, dealer_id: str) -> float:
    """历史保修申请次数 (该经销商订单的设备)"""
    stmt = select(func.count()).select_from(WarrantyRecord).join(
        OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id
    ).where(
        OrderInfo.dealer_id == dealer_id,
        WarrantyRecord.issue_type == '保修申请',
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dealer_repair_count(db: AsyncSession, dealer_id: str) -> float:
    """历史维修次数 (该经销商订单的设备)"""
    stmt = select(func.count()).select_from(WarrantyRecord).join(
        OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id
    ).where(
        OrderInfo.dealer_id == dealer_id,
        WarrantyRecord.issue_type == '维修',
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dealer_cross_region_report_count(db: AsyncSession, dealer_id: str) -> float:
    """该经销商被举报跨区次数"""
    return await _count(db, CrossRegionReport, dealer_id=dealer_id)


async def _feat_dealer_blacklist_hit(db: AsyncSession, dealer_id: str) -> float:
    """是否黑名单经销商 (0/1).

    查两张黑名单:
      1. 风控黑名单 risk_blacklist (类型=经销商ID, 未过期, 未软删)
      2. 业务黑名单 blacklist_extra (类型=经销商ID, 未过期)
    任意一张命中 → 1.
    """
    now = datetime.now()
    # 1. 风控黑名单
    bl = (await db.execute(
        select(RiskBlacklist.blacklist_id).where(
            RiskBlacklist.blacklist_type == "经销商ID",
            RiskBlacklist.blacklist_value == dealer_id,
            RiskBlacklist.deleted_at.is_(None),
        ).limit(1)
    )).scalar_one_or_none()
    if bl:
        return 1.0
    # 2. 业务黑名单 (需查 expire_at)
    row = (await db.execute(
        select(BlacklistExtra.expire_at).where(
            BlacklistExtra.type == "经销商ID",
            BlacklistExtra.value == dealer_id,
        ).limit(1)
    )).first()
    if row:
        if row.expire_at is None or row.expire_at > now:
            return 1.0
    return 0.0


# ============================================================
# 订单(订货)维度特征 (6 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """订单总金额"""
    row = (await db.execute(
        select(OrderInfo.total_amount).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.total_amount) if row and row.total_amount is not None else 0


async def _feat_order_quantity(db: AsyncSession, order_id: str) -> float:
    """订单产品数量"""
    row = (await db.execute(
        select(OrderInfo.quantity).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.quantity) if row and row.quantity is not None else 0


async def _feat_order_unit_price(db: AsyncSession, order_id: str) -> float:
    """成交单价"""
    row = (await db.execute(
        select(OrderInfo.unit_price).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.unit_price) if row and row.unit_price is not None else 0


async def _feat_order_is_first(db: AsyncSession, order_id: str) -> float:
    """是否经销商首单 (0/1): 该经销商没有比这张更早的订单"""
    row = (await db.execute(
        select(OrderInfo.dealer_id, OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not row:
        return 0.0
    earlier = (await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.dealer_id == row.dealer_id,
            OrderInfo.create_time < row.create_time,
        )
    )).scalar() or 0
    return 1.0 if earlier == 0 else 0.0


async def _feat_order_cross_region_report_count(db: AsyncSession, order_id: str) -> float:
    """该订单被举报跨区次数"""
    return await _count(db, CrossRegionReport, order_id=order_id)


async def _feat_order_cross_region_flag(db: AsyncSession, order_id: str) -> float:
    """收货区域 ≠ 经销商授权区域 (0/1), 串货核心信号"""
    row = (await db.execute(
        select(OrderInfo.ship_to_region, OrderInfo.dealer_id).where(OrderInfo.order_id == order_id)
    )).first()
    if not row or not row.ship_to_region:
        return 0.0
    drow = (await db.execute(
        select(DealerInfo.region).where(DealerInfo.dealer_id == row.dealer_id)
    )).first()
    if not drow or not drow.region:
        return 0.0
    return 1.0 if row.ship_to_region != drow.region else 0.0


# ============================================================
# 产品维度特征 (3 个)
# ============================================================

async def _feat_product_msrp(db: AsyncSession, product_id: str) -> float:
    """产品官方价 MSRP"""
    row = (await db.execute(
        select(Product.msrp).where(Product.product_id == product_id)
    )).first()
    return float(row.msrp) if row and row.msrp is not None else 0


async def _feat_product_warranty_months(db: AsyncSession, product_id: str) -> float:
    """保修期(月)"""
    row = (await db.execute(
        select(Product.warranty_months).where(Product.product_id == product_id)
    )).first()
    return float(row.warranty_months) if row and row.warranty_months is not None else 0


async def _feat_product_age_months(db: AsyncSession, order_id: str) -> float:
    """设备已使用月数 (自下单到现在的月数), 无订单返回 0"""
    if not order_id:
        return 0
    row = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time:
        return round(_months_between(row.create_time, datetime.now()), 2)
    return 0


# ============================================================
# 保修/维修维度特征 (5 个)
# ============================================================

async def _feat_warranty_is_expired(
    db: AsyncSession, warranty_id: str, order_id: str, warranty_months: float,
) -> float:
    """本次申请/维修时设备是否已过保修 (0/1).

    过期判定: 下单时间 + 保修期(月) < 本次 issue_date
    (保修期从购买日起算, 到申请时已经用完了)
    """
    wrow = (await db.execute(
        select(WarrantyRecord.issue_date).where(WarrantyRecord.warranty_id == warranty_id)
    )).first()
    if not wrow or not wrow.issue_date:
        return 0.0
    orow = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not orow or not orow.create_time or warranty_months <= 0:
        return 0.0
    purchase = orow.create_time
    expired_at = purchase + timedelta(days=warranty_months * 30)
    return 1.0 if expired_at < wrow.issue_date else 0.0


async def _feat_warranty_apply_count_30d(db: AsyncSession, product_sn: str) -> float:
    """近 30 天同 SN 保修申请次数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(WarrantyRecord).where(
        WarrantyRecord.product_sn == product_sn,
        WarrantyRecord.issue_type == '保修申请',
        WarrantyRecord.issue_date >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_sn_repair_count_90d(db: AsyncSession, product_sn: str) -> float:
    """同一 SN 近 90 天维修次数 (套保嫌疑核心特征)"""
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.count()).select_from(WarrantyRecord).where(
        WarrantyRecord.product_sn == product_sn,
        WarrantyRecord.issue_type == '维修',
        WarrantyRecord.issue_date >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_warranty_repair_cost(db: AsyncSession, warranty_id: str) -> float:
    """本次维修费用"""
    row = (await db.execute(
        select(WarrantyRecord.repair_cost).where(WarrantyRecord.warranty_id == warranty_id)
    )).first()
    return float(row.repair_cost) if row and row.repair_cost is not None else 0


def _feat_repair_cost_msrp_ratio(
    repair_cost: float, msrp: float,
) -> float:
    """维修费用占 MSRP 比例 (纯计算, 无 SQL, 同步函数)"""
    if msrp <= 0:
        return 0
    return round(repair_cost / msrp, 4)


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_dealer_features(db: AsyncSession, dealer_id: str) -> dict[str, float]:
    """计算 12 个经销商维度特征."""
    total_orders = await _feat_dealer_total_orders(db, dealer_id)

    independent = {
        "dealer_orders_30d": _feat_dealer_orders_30d,
        "dealer_orders_7d": _feat_dealer_orders_7d,
        "dealer_total_amount": _feat_dealer_total_amount,
        "dealer_max_order_amount": _feat_dealer_max_order_amount,
        "dealer_contract_days": _feat_dealer_contract_days,
        "dealer_contract_expired": _feat_dealer_contract_expired,
        "dealer_warranty_count": _feat_dealer_warranty_count,
        "dealer_repair_count": _feat_dealer_repair_count,
        "dealer_cross_region_report_count": _feat_dealer_cross_region_report_count,
        "dealer_blacklist_hit": _feat_dealer_blacklist_hit,
    }
    features = {name: await fn(db, dealer_id) for name, fn in independent.items()}
    features["dealer_total_orders"] = total_orders
    features["dealer_avg_order_amount"] = await _feat_dealer_avg_order_amount(
        db, dealer_id, total_orders=total_orders,
    )
    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 6 个订单维度特征."""
    return {
        "order_total_amount": await _feat_order_total_amount(db, order_id),
        "order_quantity": await _feat_order_quantity(db, order_id),
        "order_unit_price": await _feat_order_unit_price(db, order_id),
        "order_is_first": await _feat_order_is_first(db, order_id),
        "order_cross_region_report_count": await _feat_order_cross_region_report_count(db, order_id),
        "order_cross_region_flag": await _feat_order_cross_region_flag(db, order_id),
    }


async def compute_product_features(
    db: AsyncSession, product_id: str, order_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个产品维度特征."""
    return {
        "product_msrp": await _feat_product_msrp(db, product_id),
        "product_warranty_months": await _feat_product_warranty_months(db, product_id),
        "product_age_months": await _feat_product_age_months(db, order_id),
    }


async def compute_warranty_features(
    db: AsyncSession, warranty_id: str, product_id: str, order_id: str,
) -> dict[str, float]:
    """计算 5 个保修/维修维度特征 (仅保修事件)."""
    wrow = (await db.execute(
        select(WarrantyRecord.product_sn).where(WarrantyRecord.warranty_id == warranty_id)
    )).first()
    product_sn = wrow.product_sn if wrow else ""
    msrp = await _feat_product_msrp(db, product_id)
    warranty_months = await _feat_product_warranty_months(db, product_id)
    repair_cost = await _feat_warranty_repair_cost(db, warranty_id)

    return {
        "warranty_is_expired": await _feat_warranty_is_expired(db, warranty_id, order_id, warranty_months),
        "warranty_apply_count_30d": await _feat_warranty_apply_count_30d(db, product_sn),
        "sn_repair_count_90d": await _feat_sn_repair_count_90d(db, product_sn),
        "warranty_repair_cost": repair_cost,
        "repair_cost_msrp_ratio": _feat_repair_cost_msrp_ratio(repair_cost, msrp),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    dealer_id: str | None = None,
    order_id: str | None = None,
    product_id: str | None = None,
    warranty_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回.

    参数约定:
      - user_id: 请求里的用户ID (经销商或举报人), 兜底当 dealer 用
      - dealer_id: 真正的经销商ID (串货举报事件是"被举报经销商")
      - order_id / product_id / warranty_id: 事件相关业务实体
    """
    dealer = dealer_id or user_id
    features = await compute_dealer_features(db, dealer)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    if product_id:
        features.update(await compute_product_features(db, product_id, order_id))
    if warranty_id:
        features.update(await compute_warranty_features(db, warranty_id, product_id or "", order_id or ""))
    return features


# ============================================================
# Demo: 展示 26 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python -m app.engine.feature
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 26 维特征名 + 字典派发表")
    print("=" * 60)

    dealer_feats = [
        ("dealer_total_orders",               "历史订货总单数"),
        ("dealer_orders_30d",                 "近30天订货数"),
        ("dealer_orders_7d",                  "近7天订货数"),
        ("dealer_total_amount",               "历史订货总金额"),
        ("dealer_avg_order_amount",           "平均订货金额"),
        ("dealer_max_order_amount",           "最大单笔订货金额"),
        ("dealer_contract_days",              "已签约天数"),
        ("dealer_contract_expired",           "合同是否过期(0/1)"),
        ("dealer_warranty_count",             "历史保修申请次数"),
        ("dealer_repair_count",               "历史维修次数"),
        ("dealer_cross_region_report_count",  "被举报跨区次数"),
        ("dealer_blacklist_hit",              "是否黑名单经销商(0/1)"),
    ]
    order_feats = [
        ("order_total_amount",                "订单总金额"),
        ("order_quantity",                    "订单产品数量"),
        ("order_unit_price",                  "成交单价"),
        ("order_is_first",                    "是否经销商首单(0/1)"),
        ("order_cross_region_report_count",   "该订单被举报跨区次数"),
        ("order_cross_region_flag",           "收货区域≠授权区域(0/1)"),
    ]
    product_feats = [
        ("product_msrp",                      "产品官方价(MSRP)"),
        ("product_warranty_months",           "保修期(月)"),
        ("product_age_months",                "设备已使用月数"),
    ]
    warranty_feats = [
        ("warranty_is_expired",               "申请时是否已过保修(0/1)"),
        ("warranty_apply_count_30d",          "近30天同SN保修申请次数"),
        ("sn_repair_count_90d",               "同SN近90天维修次数"),
        ("warranty_repair_cost",              "本次维修费用"),
        ("repair_cost_msrp_ratio",            "维修费用占MSRP比例"),
    ]
    all_groups = [
        ("经销商 (12)", dealer_feats),
        ("订单 (6)", order_feats),
        ("产品 (3)", product_feats),
        ("保修 (5)", warranty_feats),
    ]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<35} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟规则 R001/R002/R005/R008/R012/R018/R025/R030 一一对应)")
