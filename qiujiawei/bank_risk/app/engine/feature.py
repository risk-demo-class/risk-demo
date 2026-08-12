"""
银行风控特征工程: 25 维特征 (3 大特征族)
- 用户维度 10 个 (user_*)
- 交易维度 8 个 (txn_*)
- 设备 IP 维度 7 个 (dev_* / ip_* / login_*)

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx    = 用户维度特征
  txn_xxx     = 交易维度特征
  dev_xxx     = 设备维度特征
  ip_xxx      = IP 维度特征
  login_xxx   = 登录维度特征
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.models import (
    BankCard,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)


# 25 维特征列名 (跟 ml_model.py 的 FEATURE_COLUMNS 一一对应)
FEATURE_COLUMNS = [
    # 用户维度 (10)
    "user_txn_count_30d",
    "user_txn_amount_30d",
    "user_avg_txn_amount",
    "user_max_txn_amount",
    "user_loan_count_6m",
    "user_login_count_7d",
    "user_login_fail_count_7d",
    "user_device_count",
    "user_credit_score",
    "user_kyc_level",
    # 交易维度 (8)
    "txn_amount",
    "txn_channel",
    "txn_is_night",
    "txn_device_age_days",
    "txn_amount_to_limit_ratio",
    "txn_hour_freq",
    "txn_to_same_card_1h",
    "txn_geo_changed",
    # 设备 IP 维度 (7)
    "dev_multi_user_count",
    "dev_risk_score",
    "ip_is_proxy",
    "ip_is_tor",
    "ip_is_new",
    "login_geo_is_new",
    "login_fail_rate_7d",
]

# 交易渠道 → 整数编码 (ML 需要数值特征; 跟 Transaction.channel 取值对齐)
_TXN_CHANNEL_MAP = {
    "online": 1, "atm": 2, "counter": 3, "mobile": 4, "pos": 5,
}

# 各维度特征子集 (compute_all_features 用 0 填充不相关的维度)
_USER_FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS if c.startswith("user_")]
_TXN_FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS if c.startswith("txn_")]
_DEVICE_IP_FEATURE_COLUMNS = [
    c for c in FEATURE_COLUMNS
    if c not in _USER_FEATURE_COLUMNS and c not in _TXN_FEATURE_COLUMNS
]


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
# 用户维度特征 (10 个)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict:
    """计算 10 个用户维度特征.

    查 user_info + transaction + loan_application + login_log + device_fingerprint.
    """
    now = datetime.now()
    since_30d = now - timedelta(days=30)
    since_7d = now - timedelta(days=7)
    since_6m = now - timedelta(days=180)

    # 1. user_txn_count_30d: 近 30 天交易数
    txn_count_30d = float((await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.txn_at >= since_30d,
        )
    )).scalar() or 0)

    # 2. user_txn_amount_30d: 近 30 天交易总金额
    txn_amount_30d = float((await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(
            Transaction
        ).where(
            Transaction.user_id == user_id,
            Transaction.txn_at >= since_30d,
        )
    )).scalar() or 0)

    # 3. user_avg_txn_amount: 平均交易金额 (所有历史)
    avg_txn_amount = float((await db.execute(
        select(func.coalesce(func.avg(Transaction.amount), 0)).select_from(
            Transaction
        ).where(Transaction.user_id == user_id)
    )).scalar() or 0)

    # 4. user_max_txn_amount: 最大单笔交易金额
    max_txn_amount = float((await db.execute(
        select(func.coalesce(func.max(Transaction.amount), 0)).select_from(
            Transaction
        ).where(Transaction.user_id == user_id)
    )).scalar() or 0)

    # 5. user_loan_count_6m: 近 6 个月贷款申请数
    loan_count_6m = float((await db.execute(
        select(func.count()).select_from(LoanApplication).where(
            LoanApplication.user_id == user_id,
            LoanApplication.apply_at >= since_6m,
        )
    )).scalar() or 0)

    # 6. user_login_count_7d: 近 7 天登录次数
    login_count_7d = float((await db.execute(
        select(func.count()).select_from(LoginLog).where(
            LoginLog.user_id == user_id,
            LoginLog.login_at >= since_7d,
        )
    )).scalar() or 0)

    # 7. user_login_fail_count_7d: 近 7 天登录失败次数 (success=0)
    login_fail_count_7d = float((await db.execute(
        select(func.count()).select_from(LoginLog).where(
            LoginLog.user_id == user_id,
            LoginLog.success == 0,
            LoginLog.login_at >= since_7d,
        )
    )).scalar() or 0)

    # 8. user_device_count: 用户关联设备数 (DISTINCT device_id)
    device_count = float((await db.execute(
        select(func.count(func.distinct(DeviceFingerprint.device_id))).select_from(
            DeviceFingerprint
        ).where(DeviceFingerprint.user_id == user_id)
    )).scalar() or 0)

    # 9. user_credit_score: 用户信用评分 (从 user_info 取)
    credit_score = float((await db.execute(
        select(UserInfo.credit_score).where(UserInfo.user_id == user_id)
    )).scalar() or 0)

    # 10. user_kyc_level: 用户 KYC 等级 (从 user_info 取)
    kyc_level = float((await db.execute(
        select(UserInfo.kyc_level).where(UserInfo.user_id == user_id)
    )).scalar() or 0)

    return {
        "user_txn_count_30d": txn_count_30d,
        "user_txn_amount_30d": txn_amount_30d,
        "user_avg_txn_amount": round(avg_txn_amount, 2),
        "user_max_txn_amount": max_txn_amount,
        "user_loan_count_6m": loan_count_6m,
        "user_login_count_7d": login_count_7d,
        "user_login_fail_count_7d": login_fail_count_7d,
        "user_device_count": device_count,
        "user_credit_score": credit_score,
        "user_kyc_level": kyc_level,
    }


# ============================================================
# 交易维度特征 (8 个)
# ============================================================

async def compute_txn_features(
    db: AsyncSession, txn_id: str, user_id: str,
) -> dict:
    """计算 8 个交易维度特征.

    查 transaction + device_fingerprint + bank_card + login_log.
    """
    # 取交易主记录
    txn = (await db.execute(
        select(Transaction).where(Transaction.txn_id == txn_id)
    )).scalar_one_or_none()

    if not txn:
        # 交易不存在, 全部填 0
        return {col: 0.0 for col in _TXN_FEATURE_COLUMNS}

    # 1. txn_amount: 交易金额
    txn_amount = float(txn.amount or 0)

    # 2. txn_channel: 交易渠道 (字符串 → 整数编码, ML 需要数值)
    txn_channel = float(_TXN_CHANNEL_MAP.get(txn.channel, 0))

    # 3. txn_is_night: 是否夜间交易 (0-5 点)
    txn_is_night = 1.0 if txn.txn_at and 0 <= txn.txn_at.hour < 5 else 0.0

    # 4. txn_device_age_days: 交易设备的使用天数 (now - device 首次出现时间)
    device_age_days = 0.0
    if txn.device_id:
        first_seen = (await db.execute(
            select(DeviceFingerprint.first_seen).where(
                DeviceFingerprint.device_id == txn.device_id,
            )
        )).scalar()
        if first_seen:
            device_age_days = max((datetime.now() - first_seen).days, 0)

    # 5. txn_amount_to_limit_ratio: 交易金额 / 银行卡额度
    #    BankCard.card_id = Transaction.from_card, 用 credit_limit
    amount_to_limit_ratio = 0.0
    if txn.from_card:
        credit_limit = (await db.execute(
            select(BankCard.credit_limit).where(BankCard.card_id == txn.from_card)
        )).scalar()
        if credit_limit and float(credit_limit) > 0:
            amount_to_limit_ratio = round(txn_amount / float(credit_limit), 4)

    # 6. txn_hour_freq: 1 小时内交易笔数 (±30 分钟窗口)
    hour_freq = 0.0
    if txn.txn_at:
        window_start = txn.txn_at - timedelta(minutes=30)
        window_end = txn.txn_at + timedelta(minutes=30)
        hour_freq = float((await db.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.txn_at >= window_start,
                Transaction.txn_at <= window_end,
            )
        )).scalar() or 0)

    # 7. txn_to_same_card_1h: 1 小时内转入同一卡数 (to_card 相同)
    to_same_card_1h = 0.0
    if txn.to_card and txn.txn_at:
        since_1h = txn.txn_at - timedelta(hours=1)
        to_same_card_1h = float((await db.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.to_card == txn.to_card,
                Transaction.txn_at >= since_1h,
                Transaction.txn_at <= txn.txn_at,
            )
        )).scalar() or 0)

    # 8. txn_geo_changed: 交易地跟用户常用登录地不同
    #    取用户最常登录的 geo, 跟当前交易 geo 比较
    txn_geo_changed = 0.0
    if txn.geo:
        most_frequent_geo = (await db.execute(
            select(LoginLog.geo).where(
                LoginLog.user_id == user_id,
                LoginLog.geo.isnot(None),
            ).group_by(LoginLog.geo).order_by(func.count().desc()).limit(1)
        )).scalar()
        if most_frequent_geo:
            txn_geo_changed = 1.0 if txn.geo != most_frequent_geo else 0.0

    return {
        "txn_amount": txn_amount,
        "txn_channel": txn_channel,
        "txn_is_night": txn_is_night,
        "txn_device_age_days": float(device_age_days),
        "txn_amount_to_limit_ratio": amount_to_limit_ratio,
        "txn_hour_freq": hour_freq,
        "txn_to_same_card_1h": to_same_card_1h,
        "txn_geo_changed": txn_geo_changed,
    }


# ============================================================
# 设备 IP 维度特征 (7 个)
# ============================================================

async def compute_device_ip_features(
    db: AsyncSession, user_id: str, device_id: str, ip: str,
) -> dict:
    """计算 7 个设备/IP 维度特征.

    查 device_fingerprint + ip_geo_location + login_log.
    device_id / ip 可能为空字符串, 对应子特征填 0.
    """
    now = datetime.now()
    since_7d = now - timedelta(days=7)

    # 1. dev_multi_user_count: 设备关联不同用户数 (DISTINCT user_id)
    dev_multi_user_count = 0.0
    if device_id:
        dev_multi_user_count = float((await db.execute(
            select(func.count(func.distinct(DeviceFingerprint.user_id))).select_from(
                DeviceFingerprint
            ).where(DeviceFingerprint.device_id == device_id)
        )).scalar() or 0)

    # 2. dev_risk_score: 设备风险评分
    dev_risk_score = 0.0
    if device_id:
        dev_risk_score = float((await db.execute(
            select(DeviceFingerprint.risk_score).where(
                DeviceFingerprint.device_id == device_id,
            )
        )).scalar() or 0)

    # 3. ip_is_proxy: IP 是否代理
    ip_is_proxy = 0.0
    if ip:
        ip_is_proxy = float((await db.execute(
            select(IpGeoLocation.is_proxy).where(IpGeoLocation.ip == ip)
        )).scalar() or 0)

    # 4. ip_is_tor: IP 是否 Tor
    ip_is_tor = 0.0
    if ip:
        ip_is_tor = float((await db.execute(
            select(IpGeoLocation.is_tor).where(IpGeoLocation.ip == ip)
        )).scalar() or 0)

    # 5. ip_is_new: IP 是否首次出现 (该用户此前没有用此 IP 登录过)
    ip_is_new = 0.0
    if ip:
        prior_ip_count = float((await db.execute(
            select(func.count()).select_from(LoginLog).where(
                LoginLog.user_id == user_id,
                LoginLog.ip == ip,
                LoginLog.login_at < now,
            )
        )).scalar() or 0)
        ip_is_new = 1.0 if prior_ip_count == 0 else 0.0

    # 6. login_geo_is_new: 登录地是否首次
    #    当前 IP 的省份 vs 用户历史登录 IP 的省份集合
    login_geo_is_new = 0.0
    if ip:
        current_province = (await db.execute(
            select(IpGeoLocation.province).where(IpGeoLocation.ip == ip)
        )).scalar()
        if current_province:
            historical_provinces = (await db.execute(
                select(func.distinct(IpGeoLocation.province)).select_from(
                    LoginLog
                ).join(
                    IpGeoLocation, LoginLog.ip == IpGeoLocation.ip
                ).where(LoginLog.user_id == user_id)
            )).scalars().all()
            login_geo_is_new = 0.0 if current_province in historical_provinces else 1.0

    # 7. login_fail_rate_7d: 近 7 天登录失败率 = 失败次数 / 总次数
    total_7d = float((await db.execute(
        select(func.count()).select_from(LoginLog).where(
            LoginLog.user_id == user_id,
            LoginLog.login_at >= since_7d,
        )
    )).scalar() or 0)
    fail_7d = float((await db.execute(
        select(func.count()).select_from(LoginLog).where(
            LoginLog.user_id == user_id,
            LoginLog.success == 0,
            LoginLog.login_at >= since_7d,
        )
    )).scalar() or 0)
    login_fail_rate_7d = round(fail_7d / total_7d, 4) if total_7d > 0 else 0.0

    return {
        "dev_multi_user_count": dev_multi_user_count,
        "dev_risk_score": dev_risk_score,
        "ip_is_proxy": ip_is_proxy,
        "ip_is_tor": ip_is_tor,
        "ip_is_new": ip_is_new,
        "login_geo_is_new": login_geo_is_new,
        "login_fail_rate_7d": login_fail_rate_7d,
    }


# ============================================================
# 聚合: 一次性算 25 维特征
# ============================================================

async def compute_all_features(
    db: AsyncSession,
    event_type: str,
    source_id: str,
    user_id: str,
    event_data: dict = None,
) -> dict:
    """根据 event_type 调用上面 3 个函数组合返回 25 维特征 dict.

    业务规则:
      - 用户特征 (10) 总是计算
      - 信用卡 / 转账: source_id = txn_id → 算交易特征 (8), 否则交易填 0
      - 设备 IP 特征 (7): device_id / ip 优先从 event_data 取,
        取不到且为交易事件时回查 transaction 记录; 都没有则填 0
    """
    event_data = event_data or {}
    features: dict = {}

    # 1. 用户维度 (10) — 总是计算
    features.update(await compute_user_features(db, user_id))

    # 2. 交易维度 (8)
    if event_type in ("信用卡", "转账") and source_id:
        features.update(await compute_txn_features(db, source_id, user_id))
    else:
        features.update({col: 0.0 for col in _TXN_FEATURE_COLUMNS})

    # 3. 设备 IP 维度 (7) — 总是尝试
    device_id = event_data.get("device_id")
    ip = event_data.get("ip")
    # 交易事件下, event_data 没带 device_id 则回查 transaction 记录
    if not device_id and source_id and event_type in ("信用卡", "转账"):
        txn_row = (await db.execute(
            select(Transaction.device_id, Transaction.ip).where(
                Transaction.txn_id == source_id,
            )
        )).first()
        if txn_row:
            device_id = txn_row.device_id
            ip = ip or txn_row.ip
    if device_id or ip:
        features.update(
            await compute_device_ip_features(db, user_id, device_id or "", ip or "")
        )
    else:
        features.update({col: 0.0 for col in _DEVICE_IP_FEATURE_COLUMNS})

    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python bank_risk/app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("银行风控特征工程 — 25 维特征名 + 分类 (3 大特征族)")
    print("=" * 60)

    user_feats = [
        ("user_txn_count_30d",       "近 30 天交易数"),
        ("user_txn_amount_30d",      "近 30 天交易总金额"),
        ("user_avg_txn_amount",      "平均交易金额"),
        ("user_max_txn_amount",      "最大单笔交易金额"),
        ("user_loan_count_6m",       "近 6 个月贷款申请数"),
        ("user_login_count_7d",      "近 7 天登录次数"),
        ("user_login_fail_count_7d", "近 7 天登录失败次数"),
        ("user_device_count",        "用户关联设备数"),
        ("user_credit_score",        "用户信用评分"),
        ("user_kyc_level",           "用户 KYC 等级"),
    ]
    txn_feats = [
        ("txn_amount",               "交易金额"),
        ("txn_channel",              "交易渠道 (整数编码)"),
        ("txn_is_night",             "是否夜间交易 (0-5 点)"),
        ("txn_device_age_days",      "交易设备使用天数"),
        ("txn_amount_to_limit_ratio","交易金额 / 银行卡额度"),
        ("txn_hour_freq",            "1 小时内交易笔数"),
        ("txn_to_same_card_1h",      "1 小时内转入同一卡数"),
        ("txn_geo_changed",          "交易地跟常用登录地不同"),
    ]
    devip_feats = [
        ("dev_multi_user_count",     "设备关联不同用户数"),
        ("dev_risk_score",           "设备风险评分"),
        ("ip_is_proxy",              "IP 是否代理"),
        ("ip_is_tor",                "IP 是否 Tor"),
        ("ip_is_new",                "IP 是否首次出现"),
        ("login_geo_is_new",         "登录地是否首次"),
        ("login_fail_rate_7d",       "近 7 天登录失败率"),
    ]
    all_groups = [
        ("用户 (10)", user_feats),
        ("交易 (8)", txn_feats),
        ("设备IP (7)", devip_feats),
    ]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<30} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")

    print("\n" + "=" * 60)
    print("结论: 3 大特征族 (用户 10 / 交易 8 / 设备IP 7) 共 25 维特征, 按 event_type 分发计算")
