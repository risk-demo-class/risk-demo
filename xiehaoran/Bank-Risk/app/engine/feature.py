"""
特征工程模块 (银行语义): 11 维银行风控纯函数特征计算.

三大特征族 (用户 / 交易 / 地址设备), 对应业务字段来自 RiskCheckRequest.event_data:
  - compute_user_features    用户特征: 多头借贷指数 / 过度查询频次 / 登录撞库频控 / 历史风险等级
  - compute_order_features   交易特征: 大额转账标记 / 分散转入对手数 / 交易时间异常度 / 金额偏离度
  - compute_address_features 地址设备特征: 地理偏离度 / IP异常评分 / 设备指纹一致性

FEATURE_ORDER 固定 11 维顺序, 与 XGBoost / 规则引擎严格对齐 (见 dec.json 输出快照).
与基线差异: 基线查 17 张电商业务表算 25 维; 银行场景事件本身即风控对象,
            特征由本模块纯函数计算 (输入 ctx 来自前端传入的事件字段).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ============================================================
# 固定 11 维特征顺序 (与 XGBoost 训练 / 规则引擎严格对齐)
# ============================================================
FEATURE_ORDER: list[str] = [
    "multi_loan_index",       # 多头借贷指数 (用户)
    "over_query_freq",        # 过度征信查询频次 (用户)
    "login_brute_freq",       # 登录撞库频控 (用户)
    "hist_risk_level",        # 历史风险等级 (用户, 0-3)
    "large_amt_flag",         # 大额转账标记 (交易, 0/1)
    "disperse_peer_cnt",      # 分散转入对手数 (交易, 归一化)
    "txn_time_anomaly",       # 交易时间异常度 (交易, 0/1)
    "amount_deviation",       # 金额偏离度 (交易, 0/1)
    "geo_deviation",          # 地理偏离度 (地址设备, 0/1)
    "ip_risk_score",          # IP 异常评分 (地址设备, 0/1)
    "device_fp_consistency",  # 设备指纹一致性 (地址设备, 0/1)
]

# 分散转入对手数归一化分母 (近 1h 对手数 / 上限 35 归一, 封顶 1.0)
_DISPERSE_PEER_DENOM = 35.0


def compute_user_features(ctx: dict) -> dict[str, float]:
    """计算用户特征族 (4 维). 输入来自 ctx 的信贷/登录字段."""
    multi_loan_index = float(ctx.get("multi_loan_index", 0.0)
                             or _derive_multi_loan(ctx))
    over_query_freq = float(ctx.get("over_query_freq", 0.0)
                            or _derive_over_query(ctx))
    login_brute_freq = float(ctx.get("login_brute_freq", 0.0)
                             or _derive_login_brute(ctx))
    hist_risk_level = float(ctx.get("hist_risk_level", 0) or 0)
    return {
        "multi_loan_index": min(multi_loan_index, 1.0),
        "over_query_freq": min(over_query_freq, 1.0),
        "login_brute_freq": min(login_brute_freq, 1.0),
        "hist_risk_level": max(0.0, min(hist_risk_level, 3.0)),
    }


def compute_order_features(ctx: dict) -> dict[str, float]:
    """计算交易/订单特征族 (4 维). 输入来自 ctx 的交易金额/对手/时间字段."""
    amount = float(ctx.get("amount") or ctx.get("txn_amt") or 0.0)
    large_amt_flag = 1.0 if amount >= 200000.0 else 0.0
    # 分散转入对手数: 优先用原始整数, 否则用已归一值
    raw_cnt = ctx.get("disperse_peer_cnt_raw") or ctx.get("counterparty_acct_cnt") or 0
    try:
        raw_cnt = float(raw_cnt)
    except (TypeError, ValueError):
        raw_cnt = 0.0
    disperse_peer_cnt = min(raw_cnt / _DISPERSE_PEER_DENOM, 1.0)
    if "disperse_peer_cnt" in ctx and ctx["disperse_peer_cnt"] not in (None, ""):
        try:
            disperse_peer_cnt = min(float(ctx["disperse_peer_cnt"]), 1.0)
        except (TypeError, ValueError):
            pass

    hour = _parse_hour(ctx)
    txn_time_anomaly = 1.0 if (hour is not None and 0 <= hour <= 6) else 0.0

    amount_deviation = 1.0 if ctx.get("amount_deviation", 0) else 0.0
    if amount >= 100000.0 and amount_deviation == 0.0:
        amount_deviation = 1.0  # 大额默认视为偏离基线

    return {
        "large_amt_flag": float(large_amt_flag),
        "disperse_peer_cnt": float(disperse_peer_cnt),
        "txn_time_anomaly": float(txn_time_anomaly),
        "amount_deviation": float(amount_deviation),
    }


def compute_address_features(ctx: dict) -> dict[str, float]:
    """计算地址/设备特征族 (3 维). 输入来自 ctx 的地理/IP/设备字段."""
    geo_deviation = 1.0 if ctx.get("geo_deviation", 0) else 0.0
    ip_risk_score = 1.0 if ctx.get("ip_risk_score", 0) else 0.0
    # 设备指纹一致性: 1 表示完全一致(安全), 0.5 表示未知/部分, 0 表示突变
    fp = ctx.get("device_fp_consistency", None)
    if fp in (None, ""):
        device_fp_consistency = 0.5
    else:
        try:
            device_fp_consistency = float(fp)
        except (TypeError, ValueError):
            device_fp_consistency = 0.5
    return {
        "geo_deviation": float(geo_deviation),
        "ip_risk_score": float(ip_risk_score),
        "device_fp_consistency": float(device_fp_consistency),
    }


def compute_all_features(
    ctx: dict,
    user_id: str | None = None,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 11 维特征并合并返回 (按 FEATURE_ORDER 顺序)."""
    features: dict[str, float] = {}
    features.update(compute_user_features(ctx))
    features.update(compute_order_features(ctx))
    features.update(compute_address_features(ctx))
    # 仅保留 FEATURE_ORDER 定义的 11 维, 维持固定顺序
    return {k: float(features.get(k, 0.0)) for k in FEATURE_ORDER}


# ============================================================
# 派生函数 (当 ctx 未显式提供时, 从原始字段推断)
# ============================================================
def _derive_multi_loan(ctx: dict) -> float:
    """多头借贷指数: 由近 N 日申贷机构数推断 (>=5 家视为高)."""
    cnt = ctx.get("loan_apply_cnt") or ctx.get("apply_org_cnt") or 0
    try:
        cnt = float(cnt)
    except (TypeError, ValueError):
        return 0.0
    return min(cnt / 5.0, 1.0)


def _derive_over_query(ctx: dict) -> float:
    """过度征信查询频次: 由 credit_query_cnt 推断 (>=10 次视为高)."""
    cnt = ctx.get("credit_query_cnt") or 0
    try:
        cnt = float(cnt)
    except (TypeError, ValueError):
        return 0.0
    return min(cnt / 10.0, 1.0)


def _derive_login_brute(ctx: dict) -> float:
    """登录撞库频控: 由近 5 分钟登录失败次数推断 (>=5 次视为高)."""
    cnt = ctx.get("login_fail_5m") or 0
    try:
        cnt = float(cnt)
    except (TypeError, ValueError):
        return 0.0
    return min(cnt / 5.0, 1.0)


def _parse_hour(ctx: dict) -> int | None:
    """从 txn_time / hour 字段解析小时."""
    if "hour" in ctx and ctx["hour"] not in (None, ""):
        try:
            return int(ctx["hour"]) % 24
        except (TypeError, ValueError):
            pass
    t = ctx.get("txn_time") or ctx.get("event_time") or ""
    if isinstance(t, str) and len(t) >= 13:
        try:
            return int(t[11:13])
        except ValueError:
            return None
    return None


def build_feature_vector(ctx: dict) -> list[float]:
    """构造与 FEATURE_ORDER 严格对齐的有序特征向量 (供 XGBoost 训练/推理).

    兼容造数脚本字段名 (f_counterparty_cnt / credit_query_30d / multi_loan_platforms /
    login_fail_5m / geo_ip_deviation) 与前端事件字段名 (counterparty_acct_cnt /
    credit_query_cnt / ...) 两种来源.
    """
    norm = dict(ctx)
    # 字段名归一化 (造数脚本 → 标准名)
    if "f_counterparty_cnt" in norm:
        norm.setdefault("counterparty_acct_cnt", norm.pop("f_counterparty_cnt"))
    if "credit_query_30d" in norm:
        norm.setdefault("credit_query_cnt", norm.pop("credit_query_30d"))
    if "multi_loan_platforms" in norm:
        norm.setdefault("apply_org_cnt", norm.pop("multi_loan_platforms"))
    if "login_fail_5m" in norm:
        norm.setdefault("login_fail_5m", norm["login_fail_5m"])
    if norm.get("geo_ip_deviation"):
        norm.setdefault("geo_deviation", 1)
    feats = compute_all_features(norm)
    return [float(feats[k]) for k in FEATURE_ORDER]
