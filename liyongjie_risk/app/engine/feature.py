"""
银行风控系统 - 特征工程模块
==========================
通过 ORM 查询业务数据, 计算 30 个银行风控特征.

【特征命名规范】
  user_xxx       = 用户维度特征 (登录习惯/交易习惯/信用画像)
  txn_xxx        = 当前交易维度特征
  device_xxx     = 设备维度特征
  ip_xxx         = IP 维度特征
  card_xxx       = 卡维度特征
  loan_xxx       = 贷款维度特征
  cntprty_xxx    = 对手方维度特征

【30 维特征列表】
  用户维度 (10 个):
    user_geo_mismatch       — 当前城市 != 常用城市 (0/1)
    user_login_fail_1h      — 近 1 小时登录失败次数
    user_txn_1h_count       — 近 1 小时交易笔数
    user_txn_0_5_count      — 近 24 小时 0-5 点交易笔数
    user_txn_24h_amount     — 近 24 小时交易总额
    user_small_txn_24h      — 近 24 小时小额(<=100)交易笔数
    user_cards_count        — 绑定银行卡数量
    user_recent_changepwd   — 近 30 分钟是否修改密码 (0/1)
    user_recent_changephone — 近 30 分钟是否换绑手机 (0/1)
    user_profile_changes_24h — 近 24h 修改资料次数

  交易维度 (8 个):
    txn_amount              — 当前交易金额
    txn_hour                — 交易小时 (0-23)
    txn_is_night            — 是否凌晨 (0-5点) (0/1)
    txn_channel             — 交易渠道编码
    txn_to_same_bank        — 是否同行转账 (0/1)
    txn_amount_near_threshold — 是否接近大额监控阈值 (0/1)
    txn_is_cross_border     — 是否跨行/跨境 (0/1)
    txn_credit_usage_ratio  — 信用卡额度使用率

  设备维度 (5 个):
    device_age_days         — 设备首次出现距今天数
    device_user_count       — 设备关联的不同用户数
    device_is_emulator      — 是否模拟器 (0/1)
    device_is_root          — 是否越狱/root (0/1)
    device_status           — 设备风险状态 (1=正常, 2=高风险, 3=黑名单)

  IP 维度 (3 个):
    ip_is_proxy             — 是否代理 IP (0/1)
    ip_is_tor               — 是否 Tor 出口 (0/1)
    ip_user_count           — IP 关联的不同用户数

  贷款维度 (4 个):
    loan_amount             — 贷款申请金额
    loan_debt_ratio         — 负债率
    loan_credit_query_1m    — 近 1 月征信查询次数
    loan_income_gap_ratio   — 收入与征信偏差率
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    UserInfo, UserProfile, BankCard, Transaction, LoginLog,
    LoanApplication, DeviceFingerprint, IpGeoLocation,
    BlacklistExtra, DeviceUserRel, RiskEvent,
)

logger = logging.getLogger(__name__)


# ============================================================
# 通用 SQL 工具
# ============================================================
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


async def _count_time_window(
    model, db: AsyncSession, time_col, hours: int, **filters
) -> float:
    """时间窗口内计数"""
    since = datetime.now() - timedelta(hours=hours)
    stmt = select(func.count()).select_from(model).where(getattr(model, time_col) >= since)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (10 个)
# ============================================================

async def _feat_user_geo_mismatch(
    db: AsyncSession, user_id: int, current_geo: str | None,
) -> float:
    """当前城市 != 常用城市 → 1, 否则 0"""
    if not current_geo:
        return 0.0
    profile = (await db.execute(
        select(UserProfile.common_city).where(UserProfile.user_id == user_id)
    )).scalar_one_or_none()
    if not profile:
        return 0.0
    # 简单比较: 提取城市名 (geo 格式: "省-市")
    current_city = current_geo.split("-")[-1] if "-" in current_geo else current_geo
    profile_city = profile.split("-")[-1] if profile and "-" in profile else (profile or "")
    return 1.0 if current_city != profile_city and profile_city else 0.0


async def _feat_user_login_fail_1h(db: AsyncSession, user_id: int) -> float:
    return await _count_time_window(LoginLog, db, "login_at", 1, user_id=user_id, success=0)


async def _feat_user_txn_1h_count(db: AsyncSession, user_id: int) -> float:
    """近 1 小时交易笔数 (从该用户的所有卡发起)"""
    since = datetime.now() - timedelta(hours=1)
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card_id == BankCard.card_id
    ).where(
        BankCard.user_id == user_id,
        Transaction.created_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_txn_0_5_count(db: AsyncSession, user_id: int) -> float:
    """近 24 小时 0-5 点交易笔数"""
    since = datetime.now() - timedelta(hours=24)
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card_id == BankCard.card_id
    ).where(
        BankCard.user_id == user_id,
        Transaction.created_at >= since,
        func.hour(Transaction.created_at).between(0, 5),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_txn_24h_amount(db: AsyncSession, user_id: int) -> float:
    since = datetime.now() - timedelta(hours=24)
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(
        Transaction
    ).join(
        BankCard, Transaction.from_card_id == BankCard.card_id
    ).where(
        BankCard.user_id == user_id,
        Transaction.created_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_small_txn_24h(db: AsyncSession, user_id: int) -> float:
    """近 24 小时小额(<=100)交易笔数"""
    since = datetime.now() - timedelta(hours=24)
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card_id == BankCard.card_id
    ).where(
        BankCard.user_id == user_id,
        Transaction.created_at >= since,
        Transaction.amount <= 100,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cards_count(db: AsyncSession, user_id: int) -> float:
    return await _count(BankCard, db, user_id=user_id)


async def _feat_user_recent_changepwd(db: AsyncSession, user_id: int) -> float:
    """近 30 分钟是否修改密码"""
    since = datetime.now() - timedelta(minutes=30)
    count = await _count_time_window(
        RiskEvent, db, "created_at", 0.5,
        user_id=user_id, event_type="CHANGE_PWD",
    )
    return 1.0 if count > 0 else 0.0


async def _feat_user_recent_changephone(db: AsyncSession, user_id: int) -> float:
    """近 30 分钟是否换绑手机"""
    since = datetime.now() - timedelta(minutes=30)
    count = await _count_time_window(
        RiskEvent, db, "created_at", 0.5,
        user_id=user_id, event_type="CHANGE_PHONE",
    )
    return 1.0 if count > 0 else 0.0


async def _feat_user_profile_changes_24h(db: AsyncSession, user_id: int) -> float:
    """近 24h 修改资料次数"""
    since = datetime.now() - timedelta(hours=24)
    stmt = select(func.count()).select_from(RiskEvent).where(
        RiskEvent.user_id == user_id,
        RiskEvent.created_at >= since,
        RiskEvent.event_type.in_(["CHANGE_PWD", "CHANGE_PHONE", "UPDATE_PROFILE"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 交易维度特征 (8 个)
# ============================================================

async def _feat_txn_amount(amount: float | None) -> float:
    return float(amount) if amount else 0.0


def _feat_txn_hour() -> float:
    return float(datetime.now().hour)


def _feat_txn_is_night() -> float:
    hour = datetime.now().hour
    return 1.0 if 0 <= hour <= 5 else 0.0


def _feat_txn_channel(channel: str | None) -> float:
    """渠道编码: APP=1, 网银=2, ATM=3, POS=4, 第三方=5"""
    mapping = {"APP": 1, "网银": 2, "ATM": 3, "POS": 4, "第三方": 5}
    return float(mapping.get(channel or "APP", 1))


async def _feat_txn_to_same_bank(
    db: AsyncSession, from_card_id: int | None, to_bank_code: str | None,
) -> float:
    if not from_card_id or not to_bank_code:
        return 0.0
    card = (await db.execute(
        select(BankCard.bank_code).where(BankCard.card_id == from_card_id)
    )).scalar_one_or_none()
    if not card:
        return 0.0
    return 1.0 if card == to_bank_code else 0.0


def _feat_txn_amount_near_threshold(amount: float | None) -> float:
    """是否接近大额监控阈值: 9000-10000, 19000-20000, 49000-50000"""
    if not amount:
        return 0.0
    thresholds = [(9000, 10000), (19000, 20000), (49000, 50000)]
    for lo, hi in thresholds:
        if lo <= amount < hi:
            return 1.0
    return 0.0


def _feat_txn_is_cross_border(to_bank_code: str | None, channel: str | None) -> float:
    """是否跨行/跨境: 跨行=1, 境外渠道=1"""
    if channel and channel in ("POS", "第三方"):
        return 0.5  # 可能是境外
    return 1.0 if to_bank_code else 0.0


async def _feat_txn_credit_usage_ratio(
    db: AsyncSession, user_id: int, amount: float | None,
) -> float:
    """信用卡额度使用率: 当前交易 / 信用卡总额度"""
    if not amount:
        return 0.0
    stmt = select(func.coalesce(func.sum(BankCard.credit_limit), 0)).where(
        BankCard.user_id == user_id,
        BankCard.card_type == 2,  # 信用卡
    )
    total_limit = float((await db.execute(stmt)).scalar() or 0)
    if total_limit <= 0:
        return 0.0
    return min(1.0, float(amount) / total_limit)


# ============================================================
# 设备维度特征 (5 个)
# ============================================================

async def _feat_device_age_days(db: AsyncSession, device_id: int | None) -> float:
    if not device_id:
        return 999.0  # 无设备 → 视为"老设备" (不触发新设备规则)
    device = (await db.execute(
        select(DeviceFingerprint.first_seen).where(
            DeviceFingerprint.device_id == device_id
        )
    )).scalar_one_or_none()
    if not device:
        return 999.0
    return float((datetime.now() - device).days)


async def _feat_device_user_count(db: AsyncSession, device_id: int | None) -> float:
    if not device_id:
        return 0.0
    return await _count(DeviceUserRel, db, device_id=device_id)


async def _feat_device_is_emulator(db: AsyncSession, device_id: int | None) -> float:
    if not device_id:
        return 0.0
    device = (await db.execute(
        select(DeviceFingerprint.is_emulator).where(DeviceFingerprint.device_id == device_id)
    )).scalar_one_or_none()
    return float(device or 0)


async def _feat_device_is_root(db: AsyncSession, device_id: int | None) -> float:
    if not device_id:
        return 0.0
    device = (await db.execute(
        select(DeviceFingerprint.is_root).where(DeviceFingerprint.device_id == device_id)
    )).scalar_one_or_none()
    return float(device or 0)


async def _feat_device_status(db: AsyncSession, device_id: int | None) -> float:
    if not device_id:
        return 1.0
    device = (await db.execute(
        select(DeviceFingerprint.status).where(DeviceFingerprint.device_id == device_id)
    )).scalar_one_or_none()
    return float(device or 1)


# ============================================================
# IP 维度特征 (3 个)
# ============================================================

async def _feat_ip_is_proxy(db: AsyncSession, ip: str | None) -> float:
    if not ip:
        return 0.0
    row = (await db.execute(
        select(IpGeoLocation.is_proxy).where(IpGeoLocation.ip == ip)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_ip_is_tor(db: AsyncSession, ip: str | None) -> float:
    if not ip:
        return 0.0
    row = (await db.execute(
        select(IpGeoLocation.is_tor).where(IpGeoLocation.ip == ip)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_ip_user_count(db: AsyncSession, ip: str | None) -> float:
    """IP 关联的不同用户数 (通过登录日志)"""
    if not ip:
        return 0.0
    stmt = select(func.count(func.distinct(LoginLog.user_id))).where(
        LoginLog.ip == ip,
        LoginLog.login_at >= (datetime.now() - timedelta(days=30)),
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 贷款维度特征 (4 个)
# ============================================================

def _feat_loan_amount(amount: float | None) -> float:
    return float(amount) if amount else 0.0


def _feat_loan_debt_ratio(debt_ratio: float | None) -> float:
    return float(debt_ratio) if debt_ratio else 0.0


def _feat_loan_credit_query_1m(queries: int | None) -> float:
    return float(queries) if queries else 0.0


def _feat_loan_income_gap_ratio(
    monthly_income: float | None, credit_score: int | None,
) -> float:
    """收入与征信偏差率: 申请收入 vs 征信收入估算"""
    if not monthly_income or monthly_income <= 0:
        return 0.0
    # 征信收入粗略估算: 信用分 / 850 * 月收入 (近似)
    estimated_income = ((credit_score or 650) / 850.0) * monthly_income
    if estimated_income <= 0:
        return 0.0
    return max(0.0, (monthly_income - estimated_income) / estimated_income)


# ============================================================
# 计算全部特征 (主入口)
# ============================================================

# 固定 30 维特征顺序 (训练和推理都用这个顺序)
FEATURE_COLUMNS: list[str] = [
    # 用户维度 (10)
    "user_geo_mismatch",
    "user_login_fail_1h",
    "user_txn_1h_count",
    "user_txn_0_5_count",
    "user_txn_24h_amount",
    "user_small_txn_24h",
    "user_cards_count",
    "user_recent_changepwd",
    "user_recent_changephone",
    "user_profile_changes_24h",
    # 交易维度 (8)
    "txn_amount",
    "txn_hour",
    "txn_is_night",
    "txn_channel",
    "txn_to_same_bank",
    "txn_amount_near_threshold",
    "txn_is_cross_border",
    "txn_credit_usage_ratio",
    # 设备维度 (5)
    "device_age_days",
    "device_user_count",
    "device_is_emulator",
    "device_is_root",
    "device_status",
    # IP 维度 (3)
    "ip_is_proxy",
    "ip_is_tor",
    "ip_user_count",
    # 贷款维度 (4)
    "loan_amount",
    "loan_debt_ratio",
    "loan_credit_query_1m",
    "loan_income_gap_ratio",
]

assert len(FEATURE_COLUMNS) == 30, f"特征数量必须是 30, 当前 {len(FEATURE_COLUMNS)}"


async def compute_all_features(
    db: AsyncSession,
    user_id: int,
    device_id: int | None = None,
    ip: str | None = None,
    geo: str | None = None,
    amount: float | None = None,
    channel: str | None = None,
    to_bank_code: str | None = None,
    from_card_id: int | None = None,
    term_months: int | None = None,
    monthly_income: float | None = None,
    debt_ratio: float | None = None,
    credit_query_1m: int | None = None,
) -> dict[str, float]:
    """
    计算全部 30 个风控特征.

    Args:
        db: 异步数据库 Session
        user_id: 用户 ID
        device_id: 设备 ID
        ip: 客户端 IP
        geo: 省市
        amount: 交易/贷款金额
        channel: 渠道
        to_bank_code: 对手方银行代码 (跨行转账)
        from_card_id: 出款卡 ID
        term_months: 贷款期限
        monthly_income: 月收入
        debt_ratio: 负债率
        credit_query_1m: 近 1 月征信查询次数

    Returns:
        30 维特征字典
    """
    # 获取用户信用分 (用于贷款特征)
    user = (await db.execute(
        select(UserInfo.credit_score).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()

    features = {
        # 用户维度
        "user_geo_mismatch": await _feat_user_geo_mismatch(db, user_id, geo),
        "user_login_fail_1h": await _feat_user_login_fail_1h(db, user_id),
        "user_txn_1h_count": await _feat_user_txn_1h_count(db, user_id),
        "user_txn_0_5_count": await _feat_user_txn_0_5_count(db, user_id),
        "user_txn_24h_amount": await _feat_user_txn_24h_amount(db, user_id),
        "user_small_txn_24h": await _feat_user_small_txn_24h(db, user_id),
        "user_cards_count": await _feat_user_cards_count(db, user_id),
        "user_recent_changepwd": await _feat_user_recent_changepwd(db, user_id),
        "user_recent_changephone": await _feat_user_recent_changephone(db, user_id),
        "user_profile_changes_24h": await _feat_user_profile_changes_24h(db, user_id),
        # 交易维度
        "txn_amount": await _feat_txn_amount(amount),
        "txn_hour": _feat_txn_hour(),
        "txn_is_night": _feat_txn_is_night(),
        "txn_channel": _feat_txn_channel(channel),
        "txn_to_same_bank": await _feat_txn_to_same_bank(db, from_card_id, to_bank_code),
        "txn_amount_near_threshold": _feat_txn_amount_near_threshold(amount),
        "txn_is_cross_border": _feat_txn_is_cross_border(to_bank_code, channel),
        "txn_credit_usage_ratio": await _feat_txn_credit_usage_ratio(db, user_id, amount),
        # 设备维度
        "device_age_days": await _feat_device_age_days(db, device_id),
        "device_user_count": await _feat_device_user_count(db, device_id),
        "device_is_emulator": await _feat_device_is_emulator(db, device_id),
        "device_is_root": await _feat_device_is_root(db, device_id),
        "device_status": await _feat_device_status(db, device_id),
        # IP 维度
        "ip_is_proxy": await _feat_ip_is_proxy(db, ip),
        "ip_is_tor": await _feat_ip_is_tor(db, ip),
        "ip_user_count": await _feat_ip_user_count(db, ip),
        # 贷款维度
        "loan_amount": _feat_loan_amount(amount),
        "loan_debt_ratio": _feat_loan_debt_ratio(debt_ratio),
        "loan_credit_query_1m": _feat_loan_credit_query_1m(credit_query_1m),
        "loan_income_gap_ratio": _feat_loan_income_gap_ratio(monthly_income, user),
    }

    logger.info(
        "特征计算完成: user_id=%d, 30 维, geo_mismatch=%.0f, txn_1h=%.0f, "
        "device_age=%.0f, ip_proxy=%.0f",
        user_id, features["user_geo_mismatch"], features["user_txn_1h_count"],
        features["device_age_days"], features["ip_is_proxy"],
    )
    return features
