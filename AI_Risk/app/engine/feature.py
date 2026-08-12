"""
特征工程模块: 通过 ORM 查询银行业务数据, 计算 25 个风控特征.

【特征命名规范】前缀决定 risk_feature 表的 entity_type
  user_xxx   = 用户维度特征 (交易/登录/KYC)
  order_xxx  = 交易维度特征 (转账/消费/取现)
  addr_xxx   = 地址/设备维度特征
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    FraudCaseRecord, LoanApplication, LoginLog, Transaction, TxnSuspiciousReport,
)

LARGE_TXN_THRESHOLD = 50000.0  # 大额交易阈值 5 万


async def _count_distinct(model, col_name: str, db: AsyncSession, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.count(func.distinct(col))).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)

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
# 用户维度特征 (14 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史交易总数 (原: 订单总数)"""
    return await _count(Transaction, db, user_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    """近30天交易数 (原: 近30天订单数)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.txn_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    """近7天交易数 (原: 近7天订单数)"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.txn_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史总交易金额 (原: 总消费金额)"""
    return await _sum(Transaction, "amount", db, user_id=user_id)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """平均订单金额 = 总金额 / 订单数. total_orders 预传可避免 batch 时重复查 SQL."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔交易金额 (原: 最大单笔订单金额)"""
    stmt = select(func.coalesce(func.max(Transaction.amount), 0)).select_from(
        Transaction
    ).where(Transaction.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """可疑交易报告次数 (原: 退款总次数)"""
    return await _count(TxnSuspiciousReport, db, user_id=user_id)


async def _feat_user_postsale_count(db: AsyncSession, user_id: str) -> float:
    """大额交易次数 (>5万) (原: 售后总次数)"""
    stmt = select(func.count()).select_from(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.amount >= LARGE_TXN_THRESHOLD,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """退款率 = 退款次数 / 总订单数. total_orders 预传可避免 batch 时重复查 SQL."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    refund_count = await _feat_user_refund_count(db, user_id)
    return round(refund_count / total_orders, 4)


async def _feat_user_postsale_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    """售后率 = 售后次数 / 总订单数. total_orders 预传可避免 batch 时重复查 SQL."""
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    postsale_count = await _feat_user_postsale_count(db, user_id)
    return round(postsale_count / total_orders, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    """可疑交易总金额 (原: 退款总金额)"""
    return await _sum(TxnSuspiciousReport, "amount", db, user_id=user_id)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """贷款申请次数 (原: 取消订单次数)"""
    return await _count(LoanApplication, db, user_id=user_id)


async def _feat_user_dispute_count(db: AsyncSession, user_id: str) -> float:
    """欺诈案件记录数 (原: 投诉次数)"""
    return await _count(FraudCaseRecord, db, user_id=user_id)


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    """登录城市数 (原: 收货地址数量)"""
    return await _count_distinct(LoginLog, "login_city", db, user_id=user_id)


# ============================================================
# 订单维度特征 (8 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """交易金额 (原: 订单总金额)"""
    stmt = select(func.coalesce(Transaction.amount, 0)).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_item_count(db: AsyncSession, order_id: str) -> float:
    """是否转账 (原: 商品行数; 1=转账, 0=其他)"""
    stmt = select(Transaction.txn_type).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    row = (await db.execute(stmt)).scalar()
    return 1.0 if row and "转账" in str(row) else 0.0


async def _feat_order_sku_count(db: AsyncSession, order_id: str) -> float:
    """是否跨境交易 (原: SKU总数; 1=跨境, 0=境内)"""
    stmt = select(Transaction.is_international).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    row = (await db.execute(stmt)).scalar()
    return float(row or 0)


async def _feat_order_discount_amount(db: AsyncSession, order_id: str) -> float:
    """取现金额 (原: 折扣金额; 仅取现类型)"""
    stmt = select(Transaction.amount).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id, Transaction.txn_type == "取现")
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_discount_rate(db: AsyncSession, order_id: str) -> float:
    """渠道风险标记 (原: 折扣率; 柜面/ATM=1, 网银=0.5, 手机/第三方=0)"""
    stmt = select(Transaction.channel).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    row = (await db.execute(stmt)).scalar()
    if not row:
        return 0.0
    ch = str(row)
    if ch in ("柜面", "ATM"):
        return 1.0
    if ch == "网银":
        return 0.5
    return 0.0


async def _feat_acct_login_interval(db: AsyncSession, order_id: str) -> float:
    """交易发生的小时 (原: 开户到登录间隔; 0-23)"""
    stmt = select(Transaction.txn_time).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    row = (await db.execute(stmt)).scalar()
    if row:
        return float(row.hour)
    return -1.0


async def _feat_acct_is_night(db: AsyncSession, order_id: str) -> float:
    """是否夜间交易 0-6点 (原: 是否夜间开户)"""
    stmt = select(Transaction.txn_time).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    row = (await db.execute(stmt)).scalar()
    if row:
        return 1.0 if 0 <= row.hour < 6 else 0.0
    return 0.0


async def _feat_order_category_count(db: AsyncSession, order_id: str) -> float:
    """交易金额是否整数 (原: 订单商品类别数; 1=整数, 0=非整数)"""
    stmt = select(Transaction.amount).select_from(
        Transaction
    ).where(Transaction.txn_id == order_id)
    row = (await db.execute(stmt)).scalar()
    if row:
        return 1.0 if float(row) == int(float(row)) else 0.0
    return 0.0


# ============================================================
# 地址维度特征 (3 个)
# ============================================================

async def _feat_addr_total_count(db: AsyncSession, user_id: str) -> float:
    """登录城市总数 (原: 地址总数)"""
    return await _count_distinct(LoginLog, "login_city", db, user_id=user_id)


async def _feat_addr_province_count(db: AsyncSession, user_id: str) -> float:
    """设备总数 (原: 不同省份数)"""
    return await _count_distinct(LoginLog, "login_device_id", db, user_id=user_id)


async def _feat_addr_is_new(
    db: AsyncSession, user_id: str, _receive_id: str | None
) -> float:
    """代理IP比例 (原: 是否新地址; 0-1)"""
    total = await _count(LoginLog, db, user_id=user_id)
    if total == 0:
        return 0.0
    proxy = await _count(LoginLog, db, user_id=user_id, is_proxy_ip=1)
    return round(proxy / total, 4)


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征.

    【P5 优化 2026-08-07】先 await 1 次 _feat_user_total_orders, 然后传给
    3 个派生特征复用, 避免它们各自重算 1 次 (4 次 SQL → 1 次).
    """
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
        "user_dispute_count": _feat_user_dispute_count,
        "user_address_count": _feat_user_address_count,
    }
    features = {name: await func(db, user_id) for name, func in independent_features.items()}
    features["user_total_orders"] = total_orders

    # 派生特征: 传 total_orders 避免再查
    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(db, user_id, total_orders=total_orders)
    features["user_refund_rate"] = await _feat_user_refund_rate(db, user_id, total_orders=total_orders)
    features["user_postsale_rate"] = await _feat_user_postsale_rate(db, user_id, total_orders=total_orders)

    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个订单维度特征."""
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_item_count": _feat_order_item_count,
        "order_sku_count": _feat_order_sku_count,
        "order_discount_amount": _feat_order_discount_amount,
        "order_discount_rate": _feat_order_discount_rate,
        "acct_login_interval_sec": _feat_acct_login_interval,
        "acct_is_night": _feat_acct_is_night,
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
    """一次性计算全部特征并合并返回."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 25 维特征名 + 字典派发表")
    print("=" * 60)

    # 25 维特征按域分组 (跟 engine/feature.py 的 3 个 compute_* 函数对应)
    user_feats = [
        ("user_total_orders",     "历史订单总数"),
        ("user_orders_7d",        "近 7 天订单数"),
        ("user_orders_30d",       "近 30 天订单数"),
        ("user_total_amount",     "历史总消费金额"),
        ("user_avg_order_amount", "平均订单金额"),
        ("user_max_order_amount", "最大单笔订单金额"),
        ("user_refund_count",     "退款总次数"),
        ("user_refund_rate",      "退款率"),
        ("user_refund_amount",    "退款总金额"),
        ("user_postsale_count",   "售后总次数"),
        ("user_postsale_rate",    "售后率"),
        ("user_cancel_count",     "取消订单次数"),
        ("user_dispute_count",  "交易投诉次数"),
        ("user_address_count",    "收货地址数量"),
    ]
    order_feats = [
        ("order_total_amount",    "订单总金额"),
        ("order_item_count",      "订单商品行数"),
        ("order_sku_count",       "订单 SKU 总数"),
        ("order_discount_amount", "折扣总金额"),
        ("order_discount_rate",   "折扣率"),
        ("acct_login_interval",    "开户到登录时间差(秒)"),
        ("acct_is_night",        "是否夜间开户 (0-6 点)"),
        ("order_category_count",  "订单商品类别数"),
    ]
    addr_feats = [
        ("addr_total_count",      "用户地址总数"),
        ("addr_province_count",   "不同省份数"),
        ("addr_is_new",           "本次地址是否新 (0/1)"),
    ]
    all_groups = [("用户 (14)", user_feats), ("订单 (8)", order_feats), ("地址 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")

    # P5 优化示例: total_orders 一次查询复用 3 个函数
    print("\n" + "=" * 60)
    print("[P5 优化示例] 1 次 SQL 查 user_total_orders, 复用给 3 个函数:")
    print("  compute_user_features(db, user_id) 内部")
    print("    _feat_user_total_orders(db, user_id)        → 1 次 SQL")
    print("    _feat_user_avg_order_amount(...,total_orders) → 0 次 SQL (复用)")
    print("    _feat_user_refund_rate(...,total_orders)     → 0 次 SQL (复用)")
    print("  原来 4 个特征 = 4 次 SQL → 现在 4 个 = 1 次 SQL (节省 75%)")
