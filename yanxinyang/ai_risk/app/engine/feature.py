# -*- coding: utf-8 -*-
"""特征引擎 —— 对应教学宝典《第 5 章：25 维特征》

🛂 类比：旅客检查项（X 光 / 安检门 / 手检 / 身份核验）

25 维 = 用户维度 14 + 学习维度 8 + 账号维度 3

关键设计（宝典 5.3）：
    · 特征值从业务表查，特征快照存 risk_feature —— 训练 ML 用快照，不受业务数据变化影响
    · **批量预取**：一次聚合查询算出多个特征（avg 由 total/count 推导），避免 N+1
    · 加新特征 = 三处同步：本文件加函数 + ml_model.FEATURE_COLUMNS 加字符串 + 重训 + 加测试
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_risk.engine.feature")

Features = Dict[str, float]

# ====================================================================== 特征字典
#: (特征名, 维度, 中文含义, 计算口径)
FEATURE_DEFS: List[Dict[str, str]] = [
    # ---------------- 用户维度 14 ----------------
    {"name": "user_total_orders", "dim": "用户", "label": "历史学习行为总数", "formula": "COUNT(学习行为记录)"},
    {"name": "user_orders_30d", "dim": "用户", "label": "近 30 天学习行为数", "formula": "COUNT(create_time >= now-30d)"},
    {"name": "user_orders_7d", "dim": "用户", "label": "近 7 天学习行为数", "formula": "COUNT(create_time >= now-7d)"},
    {"name": "user_total_amount", "dim": "用户", "label": "历史学习投入总额", "formula": "SUM(投入金额)"},
    {"name": "user_avg_order_amount", "dim": "用户", "label": "平均单次投入", "formula": "投入 / 行为总数"},
    {"name": "user_max_order_amount", "dim": "用户", "label": "最大单次投入", "formula": "MAX(投入金额)"},
    {"name": "user_refund_count", "dim": "用户", "label": "成绩申诉次数", "formula": "COUNT(申诉记录)"},
    {"name": "user_refund_amount", "dim": "用户", "label": "成绩申诉涉及金额", "formula": "SUM(申诉金额)"},
    {"name": "user_refund_rate", "dim": "用户", "label": "成绩申诉率", "formula": "申诉次数 / 行为总数"},
    {"name": "user_postsale_count", "dim": "用户", "label": "退课次数", "formula": "COUNT(退课记录)"},
    {"name": "user_postsale_rate", "dim": "用户", "label": "退课率", "formula": "退课数 / 行为总数"},
    {"name": "user_cancel_count", "dim": "用户", "label": "取消选课数", "formula": "COUNT(取消记录)"},
    {"name": "user_complaint_count", "dim": "用户", "label": "反馈/投诉次数", "formula": "COUNT(反馈 + 成绩申诉)"},
    {"name": "user_address_count", "dim": "用户", "label": "关联账号/设备数", "formula": "COUNT(关联实体)"},
    # ---------------- 学习维度 8 ----------------
    {"name": "order_total_amount", "dim": "学习", "label": "单次学习投入金额", "formula": "学习记录.投入金额"},
    {"name": "order_item_count", "dim": "学习", "label": "单次行为明细数", "formula": "COUNT(行为明细)"},
    {"name": "order_sku_count", "dim": "学习", "label": "单次资源种类数", "formula": "COUNT(DISTINCT 资源 ID)"},
    {"name": "order_discount_amount", "dim": "学习", "label": "优惠金额", "formula": "学习记录.优惠金额"},
    {"name": "order_discount_rate", "dim": "学习", "label": "优惠率", "formula": "优惠 / (投入 + 优惠)"},
    {"name": "order_pay_interval", "dim": "学习", "label": "交卷耗时(秒)", "formula": "提交时间 - 开始时间"},
    {"name": "order_is_night", "dim": "学习", "label": "是否深夜学习 0/1", "formula": "hour(开始时间) in [0,6)"},
    {"name": "order_category_count", "dim": "学习", "label": "单次资源分类数", "formula": "COUNT(DISTINCT 资源分类)"},
    # ---------------- 账号维度 3 ----------------
    {"name": "addr_total_count", "dim": "账号", "label": "关联实体总数", "formula": "COUNT(关联实体)"},
    {"name": "addr_province_count", "dim": "账号", "label": "跨地域数", "formula": "COUNT(DISTINCT 地域)"},
    {"name": "addr_is_new", "dim": "账号", "label": "是否新关联实体 0/1", "formula": "关联实体 7 天内新增"},
]

FEATURE_NAMES: List[str] = [f["name"] for f in FEATURE_DEFS]
FEATURE_DIM: Dict[str, str] = {f["name"]: f["dim"] for f in FEATURE_DEFS}
FEATURE_LABEL: Dict[str, str] = {f["name"]: f["label"] for f in FEATURE_DEFS}
USER_FEATURES = [f["name"] for f in FEATURE_DEFS if f["dim"] == "用户"]
ORDER_FEATURES = [f["name"] for f in FEATURE_DEFS if f["dim"] == "学习"]
ADDR_FEATURES = [f["name"] for f in FEATURE_DEFS if f["dim"] == "账号"]

assert len(FEATURE_DEFS) == 25, "特征必须是 25 维（宝典 1.3）"
assert (len(USER_FEATURES), len(ORDER_FEATURES), len(ADDR_FEATURES)) == (14, 8, 3), \
    "维度分布必须是 14 用户 + 8 学习 + 3 账号"

NEW_ADDRESS_DAYS = 7           # addr_is_new 判定窗口


# ====================================================================== 工具
def _f(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ====================================================================== 用户维度 14
def compute_user_features(db: Any, user_id: str, now: datetime) -> Features:
    """一次聚合查询算 6 个订单类特征（批量预取，避免 N+1）。"""
    d30, d7 = _fmt(now - timedelta(days=30)), _fmt(now - timedelta(days=7))
    order_agg = db.fetch_one(
        """
        SELECT COUNT(*)                                        AS total_orders,
               COALESCE(SUM(total_amount), 0)                   AS total_amount,
               COALESCE(MAX(total_amount), 0)                   AS max_amount,
               COALESCE(SUM(CASE WHEN create_time >= ? THEN 1 ELSE 0 END), 0) AS orders_30d,
               COALESCE(SUM(CASE WHEN create_time >= ? THEN 1 ELSE 0 END), 0) AS orders_7d
        FROM order_info
        WHERE user_id = ? AND deleted_at IS NULL
        """, [d30, d7, user_id]) or {}

    total_orders = _f(order_agg.get("total_orders"))
    total_amount = _f(order_agg.get("total_amount"))

    refund = db.fetch_one(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(refund_amount),0) AS amt "
        "FROM refund_record WHERE user_id = ? AND refund_status = '成功'", [user_id]) or {}
    postsale_count = _f(db.scalar("SELECT COUNT(*) FROM postsale WHERE user_id = ?", [user_id]))
    cancel_count = _f(db.scalar("SELECT COUNT(*) FROM cancel_record WHERE user_id = ?", [user_id]))
    complaint_count = _f(db.scalar("SELECT COUNT(*) FROM complaint_record WHERE user_id = ?", [user_id])) \
        + _f(db.scalar("SELECT COUNT(*) FROM logistics_complaints_record WHERE user_id = ?", [user_id]))
    address_count = _f(db.scalar(
        "SELECT COUNT(*) FROM user_address WHERE user_id = ? AND deleted_at IS NULL", [user_id]))

    refund_count = _f(refund.get("cnt"))
    # avg 由 total/count 推导（宝典 5.3：avg_order_amount 接受 total_orders 参数，避免二次查询）
    avg_amount = round(total_amount / total_orders, 4) if total_orders > 0 else 0.0
    refund_rate = round(refund_count / total_orders, 4) if total_orders > 0 else 0.0
    postsale_rate = round(postsale_count / total_orders, 4) if total_orders > 0 else 0.0

    return {
        "user_total_orders": total_orders,
        "user_orders_30d": _f(order_agg.get("orders_30d")),
        "user_orders_7d": _f(order_agg.get("orders_7d")),
        "user_total_amount": total_amount,
        "user_avg_order_amount": avg_amount,
        "user_max_order_amount": _f(order_agg.get("max_amount")),
        "user_refund_count": refund_count,
        "user_refund_amount": _f(refund.get("amt")),
        "user_refund_rate": refund_rate,
        "user_postsale_count": postsale_count,
        "user_postsale_rate": postsale_rate,
        "user_cancel_count": cancel_count,
        "user_complaint_count": complaint_count,
        "user_address_count": address_count,
    }


# ====================================================================== 学习维度 8
def compute_order_features(db: Any, order_id: Optional[str]) -> Features:
    """订单不存在（如纯用户级事件）时全部返回 0 —— 规则侧 unknown 值不命中。"""
    empty = {name: 0.0 for name in ORDER_FEATURES}
    if not order_id:
        return empty

    order = db.fetch_one(
        "SELECT total_amount, discount_amount, create_time, pay_time "
        "FROM order_info WHERE order_id = ? AND deleted_at IS NULL", [order_id])
    if not order:
        return empty

    item_agg = db.fetch_one(
        """
        SELECT COUNT(*)                       AS item_count,
               COUNT(DISTINCT oi.sku_id)      AS sku_count,
               COUNT(DISTINCT p.category_id)  AS category_count
        FROM order_item oi
        LEFT JOIN product_info p ON p.product_id = oi.product_id
        WHERE oi.order_id = ?
        """, [order_id]) or {}

    total_amount = _f(order.get("total_amount"))
    discount = _f(order.get("discount_amount"))
    original = total_amount + discount
    discount_rate = round(discount / original, 4) if original > 0 else 0.0

    created, paid = _parse_dt(order.get("create_time")), _parse_dt(order.get("pay_time"))
    pay_interval = _f((paid - created).total_seconds()) if created and paid else 0.0
    is_night = 1.0 if created and 0 <= created.hour < 6 else 0.0

    return {
        "order_total_amount": total_amount,
        "order_item_count": _f(item_agg.get("item_count")),
        "order_sku_count": _f(item_agg.get("sku_count")),
        "order_discount_amount": discount,
        "order_discount_rate": discount_rate,
        "order_pay_interval": max(pay_interval, 0.0),
        "order_is_night": is_night,
        "order_category_count": _f(item_agg.get("category_count")),
    }


# ====================================================================== 账号维度 3
def compute_address_features(db: Any, user_id: str, receive_id: Optional[str],
                             now: datetime) -> Features:
    agg = db.fetch_one(
        "SELECT COUNT(*) AS total, COUNT(DISTINCT province) AS provinces "
        "FROM user_address WHERE user_id = ? AND deleted_at IS NULL", [user_id]) or {}

    is_new = 0.0
    if receive_id:
        row = db.fetch_one(
            "SELECT create_time FROM user_address WHERE address_id = ? AND user_id = ?",
            [receive_id, user_id])
        created = _parse_dt(row.get("create_time")) if row else None
        if created and (now - created) <= timedelta(days=NEW_ADDRESS_DAYS):
            is_new = 1.0
    return {
        "addr_total_count": _f(agg.get("total")),
        "addr_province_count": _f(agg.get("provinces")),
        "addr_is_new": is_new,
    }


# ====================================================================== 汇总
def compute_all_features(db: Any, ctx: Dict[str, Any]) -> Features:
    """25 维特征总入口（流水线步骤 3）。

    ctx 至少包含：user_id / order_id / receive_id / event_time
    """
    user_id = str(ctx.get("user_id") or "")
    now = _parse_dt(ctx.get("event_time")) or datetime.now()
    features: Features = {}
    features.update(compute_user_features(db, user_id, now))
    features.update(compute_order_features(db, ctx.get("order_id")))
    features.update(compute_address_features(db, user_id, ctx.get("receive_id"), now))

    missing = [name for name in FEATURE_NAMES if name not in features]
    for name in missing:                     # 兜底补 0，保证永远 25 维
        features[name] = 0.0
    if missing:
        logger.warning("特征缺失已补 0: %s", missing)
    return {name: features[name] for name in FEATURE_NAMES}


def build_feature_rows(event_id: str, features: Features) -> List[Dict[str, Any]]:
    """25 维特征 → 25 条 risk_feature 记录（流水线步骤 4 的特征快照）。"""
    return [{"event_id": event_id, "feature_name": name,
             "feature_value": features.get(name, 0.0), "feature_dim": FEATURE_DIM[name]}
            for name in FEATURE_NAMES]
