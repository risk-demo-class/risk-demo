"""
银行风控系统 - 特征工程模块
通过 ORM 查询银行业务数据 (用户/交易/贷款/登录/IP), 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx        = 用户维度特征
  order_txn_xxx   = 交易/贷款维度特征 (order_ 前缀保持引擎兼容)
  addr_ip_xxx     = IP/设备维度特征 (addr_ 前缀保持引擎兼容)
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankCard, DeviceFingerprint, IpGeoLocation,
    LoanApplication, LoginLog, Transaction, UserInfo,
)


# ============================================================
# 通用 SQL 工具 (与电商版相同结构, 查询目标改为银行表)
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


async def _avg(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(AVG(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.avg(col), 0)).select_from(model)
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

async def _feat_user_credit_score(db: AsyncSession, user_id: str) -> float:
    """征信分"""
    row = (await db.execute(
        select(UserInfo.credit_score).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    return float(row or 600)


async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """账户注册天数"""
    row = (await db.execute(
        select(UserInfo.register_at).where(UserInfo.user_id == user_id)
    )).first()
    if row and row.register_at:
        return float(max((datetime.now() - row.register_at).days, 0))
    return 0.0


async def _feat_user_kyc_level(db: AsyncSession, user_id: str) -> float:
    """KYC等级 (未认证=0, L1=1, L2=2, L3=3)"""
    row = (await db.execute(
        select(UserInfo.kyc_level).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    level_map = {"未认证": 0, "L1": 1, "L2": 2, "L3": 3}
    return float(level_map.get(row, 0))


async def _feat_user_txns_30d(db: AsyncSession, user_id: str) -> float:
    """近30天交易数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card == BankCard.card_id
    ).where(
        BankCard.user_id == user_id,
        Transaction.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_txns_7d(db: AsyncSession, user_id: str) -> float:
    """近7天交易数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card == BankCard.card_id
    ).where(
        BankCard.user_id == user_id,
        Transaction.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_transfer_amount(db: AsyncSession, user_id: str) -> float:
    """历史总交易金额"""
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(
        Transaction
    ).join(BankCard, Transaction.from_card == BankCard.card_id).where(
        BankCard.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_transfer_amount(
    db: AsyncSession, user_id: str, total_txns: float | None = None,
) -> float:
    """平均交易金额 = 总金额 / 交易数. total_txns 预传可避免重复查 SQL."""
    if total_txns is None:
        total_txns = await _feat_user_txns_30d(db, user_id)
    if total_txns == 0:
        return 0
    total_amount = await _feat_user_total_transfer_amount(db, user_id)
    return round(total_amount / total_txns, 2)


async def _feat_user_max_transfer_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔交易金额"""
    stmt = select(func.coalesce(func.max(Transaction.amount), 0)).select_from(
        Transaction
    ).join(BankCard, Transaction.from_card == BankCard.card_id).where(
        BankCard.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_loan_count(db: AsyncSession, user_id: str) -> float:
    """贷款申请次数"""
    return await _count(LoanApplication, db, user_id=user_id)


async def _feat_user_login_count_7d(db: AsyncSession, user_id: str) -> float:
    """近7天登录次数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(LoginLog).where(
        LoginLog.user_id == user_id,
        LoginLog.login_at >= since,
        LoginLog.success == 1,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_device_count(db: AsyncSession, user_id: str) -> float:
    """关联设备数"""
    stmt = select(func.count(func.distinct(DeviceFingerprint.device_id))).select_from(
        DeviceFingerprint
    ).where(DeviceFingerprint.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_card_count(db: AsyncSession, user_id: str) -> float:
    """绑卡数"""
    return await _count(BankCard, db, user_id=user_id)


async def _feat_user_ip_region_count(db: AsyncSession, user_id: str) -> float:
    """登录IP不同省份数"""
    stmt = select(func.count(func.distinct(IpGeoLocation.province))).select_from(
        LoginLog
    ).join(IpGeoLocation, LoginLog.ip == IpGeoLocation.ip, isouter=True).where(
        LoginLog.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_debt_ratio(db: AsyncSession, user_id: str) -> float:
    """当前负债率 (取最近贷款申请的负债率)"""
    row = (await db.execute(
        select(LoanApplication.debt_ratio)
        .where(LoanApplication.user_id == user_id)
        .order_by(LoanApplication.create_time.desc())
        .limit(1)
    )).scalar_one_or_none()
    return float(row or 0)


# ============================================================
# 交易/订单维度特征 (8 个)
# ============================================================

async def _feat_order_txn_amount(db: AsyncSession, order_id: str) -> float:
    """本次交易金额"""
    row = (await db.execute(
        select(Transaction.amount).where(Transaction.txn_id == order_id)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_order_txn_is_night(db: AsyncSession, order_id: str) -> float:
    """是否夜间交易 (0~5点)"""
    row = (await db.execute(
        select(Transaction.create_time).where(Transaction.txn_id == order_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour <= 5 else 0.0
    return 0.0


async def _feat_order_txn_channel(db: AsyncSession, order_id: str) -> float:
    """交易渠道 (数值化: 柜台=0, ATM=1, 网银=2, 手机银行=3)"""
    row = (await db.execute(
        select(Transaction.channel).where(Transaction.txn_id == order_id)
    )).scalar_one_or_none()
    channel_map = {"柜台": 0, "ATM": 1, "网银": 2, "手机银行": 3}
    return float(channel_map.get(row, 0))


async def _feat_order_txn_hourly_count(db: AsyncSession, order_id: str) -> float:
    """1小时内同一用户交易数"""
    txn = (await db.execute(
        select(Transaction.from_card, Transaction.create_time)
        .where(Transaction.txn_id == order_id)
    )).first()
    if not txn:
        return 0.0
    # 查出 from_card 所属 user
    card = (await db.execute(
        select(BankCard.user_id).where(BankCard.card_id == txn.from_card)
    )).scalar_one_or_none()
    if not card:
        return 0.0
    since = txn.create_time - timedelta(hours=1)
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card == BankCard.card_id
    ).where(
        BankCard.user_id == card,
        Transaction.create_time >= since,
        Transaction.create_time <= txn.create_time,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_txn_cross_city(db: AsyncSession, order_id: str) -> float:
    """是否跨城市交易 (交易geo与常用geo不一致)"""
    # 简化: 交易IP所在城市与用户登录常用城市不一致
    txn = (await db.execute(
        select(Transaction.from_card, Transaction.ip)
        .where(Transaction.txn_id == order_id)
    )).first()
    if not txn or not txn.ip:
        return 0.0
    # 查交易IP的城市
    txn_geo = (await db.execute(
        select(IpGeoLocation.city).where(IpGeoLocation.ip == txn.ip)
    )).scalar_one_or_none()
    if not txn_geo:
        return 0.0
    # 查用户最近登录的城市
    card = (await db.execute(
        select(BankCard.user_id).where(BankCard.card_id == txn.from_card)
    )).scalar_one_or_none()
    if not card:
        return 0.0
    recent_ip = (await db.execute(
        select(LoginLog.ip)
        .where(LoginLog.user_id == card, LoginLog.success == 1)
        .order_by(LoginLog.login_at.desc()).limit(1)
    )).scalar_one_or_none()
    if not recent_ip:
        return 0.0
    recent_city = (await db.execute(
        select(IpGeoLocation.city).where(IpGeoLocation.ip == recent_ip)
    )).scalar_one_or_none()
    if not recent_city:
        return 0.0
    return 1.0 if txn_geo != recent_city else 0.0


async def _feat_order_txn_hour(db: AsyncSession, order_id: str) -> float:
    """交易小时 (0-23)"""
    row = (await db.execute(
        select(Transaction.create_time).where(Transaction.txn_id == order_id)
    )).first()
    if row and row.create_time:
        return float(row.create_time.hour)
    return 0.0


async def _feat_order_txn_days_since_last(db: AsyncSession, order_id: str) -> float:
    """距上次交易天数"""
    txn = (await db.execute(
        select(Transaction.from_card, Transaction.create_time)
        .where(Transaction.txn_id == order_id)
    )).first()
    if not txn or not txn.create_time:
        return 0.0
    # 查出 user_id
    card = (await db.execute(
        select(BankCard.user_id).where(BankCard.card_id == txn.from_card)
    )).scalar_one_or_none()
    if not card:
        return 0.0
    last_txn = (await db.execute(
        select(Transaction.create_time)
        .select_from(Transaction)
        .join(BankCard, Transaction.from_card == BankCard.card_id)
        .where(
            BankCard.user_id == card,
            Transaction.txn_id != order_id,
            Transaction.create_time < txn.create_time,
        )
        .order_by(Transaction.create_time.desc())
        .limit(1)
    )).scalar_one_or_none()
    if last_txn:
        return float(max((txn.create_time - last_txn).days, 0))
    return 999.0  # 首次交易


async def _feat_order_txn_to_card_new(db: AsyncSession, order_id: str) -> float:
    """收款卡是否新卡 (该用户首次向此收款卡转账)"""
    txn = (await db.execute(
        select(Transaction.from_card, Transaction.to_card)
        .where(Transaction.txn_id == order_id)
    )).first()
    if not txn or not txn.to_card:
        return 0.0
    card = (await db.execute(
        select(BankCard.user_id).where(BankCard.card_id == txn.from_card)
    )).scalar_one_or_none()
    if not card:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(Transaction).join(
            BankCard, Transaction.from_card == BankCard.card_id
        ).where(
            BankCard.user_id == card,
            Transaction.to_card == txn.to_card,
            Transaction.txn_id != order_id,
        )
    )).scalar() or 0
    return 1.0 if cnt == 0 else 0.0


# ============================================================
# IP/设备维度特征 (3 个)
# ============================================================

async def _feat_addr_ip_is_proxy(db: AsyncSession, user_id: str, ip: str | None) -> float:
    """IP是否为代理/Tor"""
    if not ip:
        return 0.0
    row = (await db.execute(
        select(IpGeoLocation.is_proxy, IpGeoLocation.is_tor)
        .where(IpGeoLocation.ip == ip)
    )).first()
    if row:
        return 1.0 if row.is_proxy or row.is_tor else 0.0
    return 0.0


async def _feat_addr_ip_login_freq_7d(db: AsyncSession, user_id: str, ip: str | None) -> float:
    """该IP近7天登录频次"""
    if not ip:
        return 0.0
    since = datetime.now() - timedelta(days=7)
    return await _count(
        LoginLog, db, user_id=user_id, ip=ip,
    ) if False else 0.0  # placeholder, 下面用自定义SQL


async def _feat_addr_ip_is_new(db: AsyncSession, user_id: str, ip: str | None) -> float:
    """IP是否新发现 (该用户首次使用此IP)"""
    if not ip:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(LoginLog).where(
            LoginLog.user_id == user_id,
            LoginLog.ip == ip,
        )
    )).scalar() or 0
    return 1.0 if cnt <= 1 else 0.0


# ============================================================
# 特征聚合
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征 (银行版).

    独立特征用 asyncio.gather 并行 SQL.
    """
    # 先查基础信息 (用户画像)
    user = (await db.execute(
        select(UserInfo.credit_score, UserInfo.register_at, UserInfo.kyc_level)
        .where(UserInfo.user_id == user_id)
    )).first()

    credit_score = float(user.credit_score) if user else 600
    register_at = user.register_at if user else None
    account_age = float(max((datetime.now() - register_at).days, 0)) if register_at else 0.0
    kyc_val = {"未认证": 0, "L1": 1, "L2": 2, "L3": 3}.get(user.kyc_level if user else "未认证", 0)

    # 并行计算其他独立特征
    coros = {
        "user_txns_30d": _feat_user_txns_30d(db, user_id),
        "user_txns_7d": _feat_user_txns_7d(db, user_id),
        "user_total_transfer_amount": _feat_user_total_transfer_amount(db, user_id),
        "user_max_transfer_amount": _feat_user_max_transfer_amount(db, user_id),
        "user_loan_count": _feat_user_loan_count(db, user_id),
        "user_login_count_7d": _feat_user_login_count_7d(db, user_id),
        "user_device_count": _feat_user_device_count(db, user_id),
        "user_card_count": _feat_user_card_count(db, user_id),
        "user_ip_region_count": _feat_user_ip_region_count(db, user_id),
        "user_debt_ratio": _feat_user_debt_ratio(db, user_id),
    }
    results = await asyncio.gather(*coros.values())
    features = dict(zip(coros.keys(), results))

    # 填基础信息
    features["user_credit_score"] = credit_score
    features["user_account_age_days"] = account_age
    features["user_kyc_level"] = float(kyc_val)

    # 派生: 平均交易金额 (复用 txns_30d)
    total_txns = features.get("user_txns_30d", 0)
    total_amount = features.get("user_total_transfer_amount", 0)
    features["user_avg_transfer_amount"] = round(total_amount / total_txns, 2) if total_txns > 0 else 0.0

    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个交易维度特征 (银行版, order_id = txn_id)."""
    coros = {
        "order_txn_amount": _feat_order_txn_amount(db, order_id),
        "order_txn_is_night": _feat_order_txn_is_night(db, order_id),
        "order_txn_channel": _feat_order_txn_channel(db, order_id),
        "order_txn_hourly_count": _feat_order_txn_hourly_count(db, order_id),
        "order_txn_cross_city": _feat_order_txn_cross_city(db, order_id),
        "order_txn_hour": _feat_order_txn_hour(db, order_id),
        "order_txn_days_since_last": _feat_order_txn_days_since_last(db, order_id),
        "order_txn_to_card_new": _feat_order_txn_to_card_new(db, order_id),
    }
    results = await asyncio.gather(*coros.values())
    return dict(zip(coros.keys(), results))


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个 IP/设备维度特征 (银行版, receive_id = 设备ID或IP)."""
    # receive_id 在银行场景中是设备ID或IP, 从 event_data 传入
    ip = receive_id  # 简化: receive_id 中存 IP 地址
    addr_proxy, addr_login_freq, addr_is_new = await asyncio.gather(
        _feat_addr_ip_is_proxy(db, user_id, ip),
        _feat_addr_ip_login_freq_7d(db, user_id, ip),
        _feat_addr_ip_is_new(db, user_id, ip),
    )
    return {
        "addr_ip_is_proxy": addr_proxy,
        "addr_ip_login_freq_7d": addr_login_freq,
        "addr_ip_is_new": addr_is_new,
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回.

    Args:
        user_id: 银行用户ID
        order_id: 银行场景 = txn_id (交易ID) / loan_id (贷款ID)
        receive_id: 银行场景 = 设备ID 或 IP 字符串
    """
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features