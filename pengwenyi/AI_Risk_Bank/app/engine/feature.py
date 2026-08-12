"""
银行风控系统 - 特征工程模块: 通过 ORM 查询业务数据, 计算 48 个银行风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户维度特征 (15 个)
  txn_xxx    = 转账维度特征 (9 个)
  login_xxx  = 登录维度特征 (7 个)
  loan_xxx   = 贷款维度特征 (9 个)
  card_xxx   = 信用卡维度特征 (8 个)

特征与规则一一对应 (R001-R030 银行规则的条件字段都在这里算),
也与 XGBoost FEATURE_COLUMNS 顺序一一对应 (ml_model.py).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankCard, BlacklistExtra, DeviceFingerprint, IpGeoLocation,
    LoanApplication, LoginLog, Transaction, UserInfo,
)


# ============================================================
# 通用 SQL 工具
# ============================================================

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


def _geo_city(geo: str | None) -> str:
    """地理位置 "省-市" → 市. 未知返回空串."""
    if not geo:
        return ""
    parts = str(geo).split("-")
    return parts[1].strip() if len(parts) > 1 else parts[0].strip()


def _hour_of(dt: datetime | None) -> int:
    return dt.hour if dt else -1


def _is_night(dt: datetime | None) -> float:
    """是否凌晨 0-5 点 (银行夜间异常操作的典型时段)"""
    h = _hour_of(dt)
    return 1.0 if 0 <= h < 6 else 0.0


# ============================================================
# 用户维度特征 (15 个)
# ============================================================

async def _feat_user_credit_score(db: AsyncSession, user_id: str) -> float:
    """人行信用分 (300-850, 银行核心授信依据)"""
    row = (await db.execute(
        select(UserInfo.credit_score).where(UserInfo.user_id == user_id)
    )).first()
    return float(row[0] or 0) if row and row[0] is not None else 0.0


async def _feat_user_kyc_level(db: AsyncSession, user_id: str) -> float:
    """KYC 等级 (1-4, 越高身份核验越严, 银行反洗钱必备)"""
    row = (await db.execute(
        select(UserInfo.kyc_level).where(UserInfo.user_id == user_id)
    )).first()
    return float(row[0] or 0) if row and row[0] is not None else 0.0


async def _feat_user_register_days(db: AsyncSession, user_id: str) -> float:
    """注册天数 (新户是欺诈高发群体, 银行对新户限额)"""
    row = (await db.execute(
        select(UserInfo.register_at).where(UserInfo.user_id == user_id)
    )).first()
    if not row or not row[0]:
        return 0.0
    return max(float((datetime.now() - row[0]).days), 0)


async def _feat_user_total_txn_amount(db: AsyncSession, user_id: str) -> float:
    """历史总交易金额 (转账/消费合计)"""
    return await _sum(
        db, Transaction, "amount",
        from_card=user_id,  # 占位, 下面用 join 重写
    ) if False else await _txn_amount_by_user(db, user_id)


async def _txn_amount_by_user(db: AsyncSession, user_id: str) -> float:
    """通过 user → bank_card → transaction 聚合用户交易额"""
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(
        Transaction
    ).join(BankCard, Transaction.from_card == BankCard.card_id).where(
        BankCard.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_txn_count(db: AsyncSession, user_id: str) -> float:
    """历史交易笔数"""
    stmt = select(func.count()).select_from(Transaction).join(
        BankCard, Transaction.from_card == BankCard.card_id
    ).where(BankCard.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_txn_amount(
    db: AsyncSession, user_id: str, total_txn_count: float | None = None,
) -> float:
    """平均交易金额 = 总金额 / 笔数"""
    if total_txn_count is None:
        total_txn_count = await _feat_user_total_txn_count(db, user_id)
    if total_txn_count == 0:
        return 0.0
    return round(await _txn_amount_by_user(db, user_id) / total_txn_count, 2)


async def _feat_user_max_txn_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔交易金额"""
    stmt = select(func.coalesce(func.max(Transaction.amount), 0)).select_from(
        Transaction
    ).join(BankCard, Transaction.from_card == BankCard.card_id).where(
        BankCard.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_loan_count(db: AsyncSession, user_id: str) -> float:
    """历史贷款申请总次数 (突击申贷是欺诈信号)"""
    return await _count(db, LoanApplication, user_id=user_id)


async def _feat_user_debt_ratio(db: AsyncSession, user_id: str) -> float:
    """负债率 (取最近一次贷款申请的 debt_ratio, 银行偿债能力核心指标)"""
    row = (await db.execute(
        select(LoanApplication.debt_ratio).where(
            LoanApplication.user_id == user_id
        ).order_by(LoanApplication.apply_time.desc()).limit(1)
    )).first()
    return float(row[0] or 0) if row and row[0] is not None else 0.0


async def _feat_user_monthly_income(db: AsyncSession, user_id: str) -> float:
    """月收入 (取最近一次贷款申请填写的 monthly_income)"""
    row = (await db.execute(
        select(LoanApplication.monthly_income).where(
            LoanApplication.user_id == user_id
        ).order_by(LoanApplication.apply_time.desc()).limit(1)
    )).first()
    return float(row[0] or 0) if row and row[0] is not None else 0.0


async def _feat_user_card_count(db: AsyncSession, user_id: str) -> float:
    """持卡数量 (每用户 N 张卡)"""
    return await _count(db, BankCard, user_id=user_id)


async def _feat_user_credit_utilization(db: AsyncSession, user_id: str) -> float:
    """信用卡额度使用率 = 信用卡消费总额 / 总授信额度 (刷卡套现/资金紧张信号)"""
    stmt = select(func.coalesce(func.sum(BankCard.credit_limit), 0)).select_from(
        BankCard
    ).where(BankCard.user_id == user_id, BankCard.card_type == "信用卡")
    total_limit = float((await db.execute(stmt)).scalar() or 0)
    if total_limit <= 0:
        return 0.0
    # 信用卡消费额: 从信用卡发出的交易
    stmt2 = select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(
        Transaction
    ).join(BankCard, Transaction.from_card == BankCard.card_id).where(
        BankCard.user_id == user_id, BankCard.card_type == "信用卡",
    )
    spent = float((await db.execute(stmt2)).scalar() or 0)
    return round(min(spent / total_limit, 3.0), 4)


async def _feat_user_failed_login_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天登录失败次数 (撞库/暴力破解信号)"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(LoginLog).where(
        LoginLog.user_id == user_id,
        LoginLog.success == 0,
        LoginLog.login_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_device_count(db: AsyncSession, user_id: str) -> float:
    """关联设备数 (设备频繁更换是账户被盗/团伙作案信号)"""
    stmt = select(func.count(func.distinct(LoginLog.device_id))).select_from(
        LoginLog
    ).where(LoginLog.user_id == user_id, LoginLog.device_id.is_not(None))
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_city_count(db: AsyncSession, user_id: str) -> float:
    """历史登录城市数 (短期多地登录 = 异常)"""
    stmt = select(func.count(func.distinct(LoginLog.geo))).select_from(
        LoginLog
    ).where(LoginLog.user_id == user_id, LoginLog.geo.is_not(None))
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 转账维度特征 (9 个)
# ============================================================

async def _txn_row(db: AsyncSession, txn_id: str):
    """取交易记录 (from_card/to_card/amount/device_id/ip/geo/txn_time)"""
    return (await db.execute(
        select(Transaction).where(Transaction.txn_id == txn_id)
    )).scalar_one_or_none()


async def _user_common_cities(db: AsyncSession, user_id: str) -> set[str]:
    """近 30 天用户常用城市 (登录成功 + 交易 geo 的并集)"""
    cities: set[str] = set()
    since = datetime.now() - timedelta(days=30)
    rows = (await db.execute(
        select(LoginLog.geo).where(
            LoginLog.user_id == user_id, LoginLog.success == 1,
            LoginLog.geo.is_not(None), LoginLog.login_at >= since,
        ).limit(200)
    )).all()
    for (geo,) in rows:
        c = _geo_city(geo)
        if c:
            cities.add(c)
    rows2 = (await db.execute(
        select(Transaction.geo).select_from(Transaction).join(
            BankCard, Transaction.from_card == BankCard.card_id
        ).where(BankCard.user_id == user_id, Transaction.geo.is_not(None),
                Transaction.txn_time >= since).limit(200)
    )).all()
    for (geo,) in rows2:
        c = _geo_city(geo)
        if c:
            cities.add(c)
    return cities


async def _geo_risk(db: AsyncSession, ip: str | None) -> float:
    """IP 命中代理库 / Tor 出口 / IP 黑名单 → 1 (秒拨/代理是黑产基础设施)"""
    if not ip:
        return 0.0
    row = (await db.execute(
        select(IpGeoLocation.is_proxy, IpGeoLocation.is_tor).where(
            IpGeoLocation.ip == ip
        )
    )).first()
    if row and (row[0] or row[1]):
        return 1.0
    # IP 黑名单 (blacklist_extra)
    hit = await _count(db, BlacklistExtra, type="IP", value=ip)
    return 1.0 if hit > 0 else 0.0


async def _device_user_count(db: AsyncSession, device_id: str | None) -> float:
    """同一 device_id 关联的不同 user_id 数 (设备多人共用 = 黑产特征)"""
    if not device_id:
        return 0.0
    stmt = select(func.count(func.distinct(LoginLog.user_id))).select_from(
        LoginLog
    ).where(LoginLog.device_id == device_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _to_card_black(db: AsyncSession, card_id: str | None) -> float:
    """收款卡是否在黑名单 (黑卡拦截, 直接一票否决)"""
    if not card_id:
        return 0.0
    return await _count(db, BlacklistExtra, type="银行卡号", value=card_id)


async def _feat_txn_1h(db: AsyncSession, user_id: str, txn_time: datetime | None):
    """1 小时内该用户交易笔数 + 总额 (凌晨密集操作/试探性小额测试)"""
    if not txn_time:
        return 0.0, 0.0
    since = txn_time - timedelta(hours=1)
    stmt = select(
        func.count(), func.coalesce(func.sum(Transaction.amount), 0),
    ).select_from(Transaction).join(
        BankCard, Transaction.from_card == BankCard.card_id
    ).where(
        BankCard.user_id == user_id, Transaction.txn_time >= since,
        Transaction.txn_time <= txn_time,
    )
    row = (await db.execute(stmt)).first()
    return (float(row[0] or 0), float(row[1] or 0)) if row else (0.0, 0.0)


async def _feat_txn_1h_into(db: AsyncSession, to_card: str | None, txn_time: datetime | None) -> float:
    """1 小时内转入同一收款卡的不同付款卡数 (多卡归集/洗钱特征)"""
    if not to_card or not txn_time:
        return 0.0
    since = txn_time - timedelta(hours=1)
    stmt = select(func.count(func.distinct(Transaction.from_card))).select_from(
        Transaction
    ).where(
        Transaction.to_card == to_card,
        Transaction.txn_time >= since,
        Transaction.txn_time <= txn_time,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _device_age_days(db: AsyncSession, device_id: str | None) -> float:
    """设备首次出现距今天数 (新设备 = 高欺诈风险, 银行对新设备交易限额)"""
    if not device_id:
        return 999.0
    row = (await db.execute(
        select(DeviceFingerprint.first_seen).where(
            DeviceFingerprint.device_id == device_id
        )
    )).first()
    if row and row[0]:
        return max(float((datetime.now() - row[0]).days), 0)
    # 表里没有 → 查最早登录记录
    row2 = (await db.execute(
        select(func.min(LoginLog.login_at)).where(LoginLog.device_id == device_id)
    )).first()
    if row2 and row2[0]:
        return max(float((datetime.now() - row2[0]).days), 0)
    return 999.0


async def compute_txn_features(
    db: AsyncSession, user_id: str, txn_id: str, from_card: str | None = None,
    to_card: str | None = None, device_id: str | None = None, ip: str | None = None,
) -> dict[str, float]:
    """计算 9 个转账维度特征."""
    txn = await _txn_row(db, txn_id)
    from_card = from_card or (txn.from_card if txn else None)
    to_card = to_card or (txn.to_card if txn else None)
    device_id = device_id or (txn.device_id if txn else None)
    ip = ip or (txn.ip if txn else None)
    txn_time = txn.txn_time if txn else None
    amount = float(txn.amount) if txn and txn.amount else 0.0
    geo = txn.geo if txn else None

    city = _geo_city(geo)
    common_cities = await _user_common_cities(db, user_id)
    city_match = 0.0
    if city and common_cities and city not in common_cities:
        city_match = 1.0
    elif not common_cities:
        # 无历史城市 → 不误报
        city_match = 0.0

    cnt_1h, amt_1h = await _feat_txn_1h(db, user_id, txn_time)
    return {
        "txn_amount": amount,
        "txn_is_night": _is_night(txn_time),
        "txn_1h_count": cnt_1h,
        "txn_1h_amount": amt_1h,
        "txn_city_match": city_match,
        "txn_geo_risk": await _geo_risk(db, ip),
        "txn_to_card_black": await _to_card_black(db, to_card),
        "txn_1h_into_count": await _feat_txn_1h_into(db, to_card, txn_time),
        "txn_device_user_count": await _device_user_count(db, device_id),
    }


# ============================================================
# 登录维度特征 (7 个)
# ============================================================

async def compute_login_features(
    db: AsyncSession, user_id: str, login_id: str,
    device_id: str | None = None, ip: str | None = None,
) -> dict[str, float]:
    """计算 7 个登录维度特征."""
    row = (await db.execute(
        select(LoginLog).where(LoginLog.login_id == login_id)
    )).scalar_one_or_none()
    device_id = device_id or (row.device_id if row else None)
    ip = ip or (row.ip if row else None)
    login_at = row.login_at if row else None
    success = float(row.success) if row and row.success is not None else 0.0
    geo = row.geo if row else None

    city = _geo_city(geo)
    common_cities = await _user_common_cities(db, user_id)
    city_match = 1.0 if (city and common_cities and city not in common_cities) else 0.0

    # 1 小时内登录次数 (包含本次)
    cnt_1h = 0.0
    if login_at:
        since = login_at - timedelta(hours=1)
        stmt = select(func.count()).select_from(LoginLog).where(
            LoginLog.user_id == user_id,
            LoginLog.login_at >= since,
            LoginLog.login_at <= login_at,
        )
        cnt_1h = float((await db.execute(stmt)).scalar() or 0)

    return {
        "login_success": success,
        "login_is_night": _is_night(login_at),
        "login_1h_count": cnt_1h,
        "login_city_match": city_match,
        "login_geo_risk": await _geo_risk(db, ip),
        "login_device_new": 1.0 if 0 <= await _device_age_days(db, device_id) < 7 else 0.0,
        "login_device_user_count": await _device_user_count(db, device_id),
    }


# ============================================================
# 贷款维度特征 (9 个)
# ============================================================

async def compute_loan_features(
    db: AsyncSession, user_id: str, loan_id: str,
    device_id: str | None = None, ip: str | None = None,
) -> dict[str, float]:
    """计算 9 个贷款维度特征 (设备/IP 从 event_data 补全)."""
    row = (await db.execute(
        select(LoanApplication).where(LoanApplication.loan_id == loan_id)
    )).scalar_one_or_none()
    apply_time = row.apply_time if row else None
    amount = float(row.amount) if row and row.amount else 0.0
    term = float(row.term_months) if row and row.term_months else 0.0
    debt_ratio = float(row.debt_ratio) if row and row.debt_ratio is not None else 0.0
    income = float(row.monthly_income) if row and row.monthly_income is not None else 0.0

    # 当月申请数 (包含本次)
    month_count = 0.0
    # 近 3 个月申请数
    m3_count = 0.0
    gap_days = 0.0
    if apply_time:
        month_start = apply_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        since_3m = apply_time - timedelta(days=90)
        stmt = select(func.count()).select_from(LoanApplication).where(
            LoanApplication.user_id == user_id, LoanApplication.apply_time >= month_start,
        )
        month_count = float((await db.execute(stmt)).scalar() or 0)
        stmt2 = select(func.count()).select_from(LoanApplication).where(
            LoanApplication.user_id == user_id, LoanApplication.apply_time >= since_3m,
        )
        m3_count = float((await db.execute(stmt2)).scalar() or 0)
        # 距上次申请天数
        prev = (await db.execute(
            select(func.max(LoanApplication.apply_time)).where(
                LoanApplication.user_id == user_id,
                LoanApplication.apply_time < apply_time,
            )
        )).scalar()
        if prev:
            gap_days = max(float((apply_time - prev).total_seconds() / 86400), 0)

    amount_income_ratio = round(amount / income, 2) if income > 0 else 0.0
    return {
        "loan_amount": amount,
        "loan_term_months": term,
        "loan_debt_ratio": debt_ratio,
        "loan_monthly_income": income,
        "loan_month_count": month_count,
        "loan_3m_count": m3_count,
        "loan_apply_gap_days": gap_days,
        "loan_amount_income_ratio": amount_income_ratio,
        "loan_geo_risk": await _geo_risk(db, ip),
    }


# ============================================================
# 信用卡维度特征 (8 个)
# ============================================================

async def compute_card_features(
    db: AsyncSession, user_id: str, card_id: str,
    device_id: str | None = None, ip: str | None = None, event_data: dict | None = None,
) -> dict[str, float]:
    """计算 8 个信用卡维度特征 (本次金额/设备/IP 从 event_data 补全)."""
    row = (await db.execute(
        select(BankCard).where(BankCard.card_id == card_id)
    )).scalar_one_or_none()
    limit = float(row.credit_limit) if row and row.credit_limit is not None else 0.0
    amount = float((event_data or {}).get("amount", 0.0)) if event_data else 0.0
    txn_time = None
    if event_data and event_data.get("txn_time"):
        try:
            txn_time = datetime.fromisoformat(str(event_data["txn_time"]))
        except ValueError:
            txn_time = None

    # 该卡近 7 天交易统计
    since = datetime.now() - timedelta(days=7)
    stmt = select(
        func.count(), func.coalesce(func.sum(Transaction.amount), 0),
        func.count(func.distinct(Transaction.geo)),
    ).select_from(Transaction).where(
        Transaction.from_card == card_id, Transaction.txn_time >= since,
    )
    stat = (await db.execute(stmt)).first()
    cnt_7d = float(stat[0] or 0) if stat else 0.0
    amt_7d = float(stat[1] or 0) if stat else 0.0
    geo_7d = float(stat[2] or 0) if stat else 0.0

    utilization = round(amt_7d / limit, 4) if limit > 0 else 0.0
    return {
        "card_amount": amount,
        "card_is_night": _is_night(txn_time),
        "card_credit_limit": limit,
        "card_utilization": min(utilization, 3.0),
        "card_7d_txn_count": cnt_7d,
        "card_7d_txn_amount": amt_7d,
        "card_geo_count_7d": geo_7d,
        "card_device_new": 1.0 if 0 <= await _device_age_days(db, device_id) < 7 else 0.0,
    }


# ============================================================
# 聚合入口
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 15 个用户维度特征."""
    total_txn_count = await _feat_user_total_txn_count(db, user_id)
    return {
        "user_credit_score": await _feat_user_credit_score(db, user_id),
        "user_kyc_level": await _feat_user_kyc_level(db, user_id),
        "user_register_days": await _feat_user_register_days(db, user_id),
        "user_total_txn_amount": await _txn_amount_by_user(db, user_id),
        "user_total_txn_count": total_txn_count,
        "user_avg_txn_amount": await _feat_user_avg_txn_amount(db, user_id, total_txn_count),
        "user_max_txn_amount": await _feat_user_max_txn_amount(db, user_id),
        "user_total_loan_count": await _feat_user_total_loan_count(db, user_id),
        "user_debt_ratio": await _feat_user_debt_ratio(db, user_id),
        "user_monthly_income": await _feat_user_monthly_income(db, user_id),
        "user_card_count": await _feat_user_card_count(db, user_id),
        "user_credit_utilization": await _feat_user_credit_utilization(db, user_id),
        "user_failed_login_7d": await _feat_user_failed_login_7d(db, user_id),
        "user_device_count": await _feat_user_device_count(db, user_id),
        "user_city_count": await _feat_user_city_count(db, user_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    event_type: str,
    source_id: str,
    from_card: str | None = None,
    to_card: str | None = None,
    device_id: str | None = None,
    ip: str | None = None,
    event_data: dict | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回 (用户 15 + 事件特征).

    事件特征按 event_type 派发; 登录/贷款/信用卡的金额等字段从 event_data 补全.
    """
    features = await compute_user_features(db, user_id)
    if event_type == "转账":
        features.update(await compute_txn_features(
            db, user_id, source_id, from_card, to_card, device_id, ip,
        ))
    elif event_type == "登录":
        features.update(await compute_login_features(db, user_id, source_id, device_id, ip))
    elif event_type == "贷款申请":
        features.update(await compute_loan_features(db, user_id, source_id, device_id, ip))
    elif event_type == "信用卡":
        features.update(await compute_card_features(
            db, user_id, source_id, device_id, ip, event_data,
        ))
    return features


# ============================================================
# Demo: 展示 48 维特征名 + 分类 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("银行特征工程 — 48 维特征名 + 分类")
    print("=" * 60)

    user_feats = [
        ("user_credit_score",        "人行信用分 (300-850)"),
        ("user_kyc_level",           "KYC 等级 (1-4)"),
        ("user_register_days",       "注册天数"),
        ("user_total_txn_amount",    "历史总交易金额"),
        ("user_total_txn_count",     "历史交易笔数"),
        ("user_avg_txn_amount",      "平均交易金额"),
        ("user_max_txn_amount",      "最大单笔交易金额"),
        ("user_total_loan_count",    "历史贷款申请次数"),
        ("user_debt_ratio",          "负债率"),
        ("user_monthly_income",      "月收入"),
        ("user_card_count",          "持卡数"),
        ("user_credit_utilization",  "信用卡额度使用率"),
        ("user_failed_login_7d",     "近 7 天登录失败次数"),
        ("user_device_count",        "关联设备数"),
        ("user_city_count",          "历史登录城市数"),
    ]
    txn_feats = [
        ("txn_amount",          "本次转账金额"),
        ("txn_is_night",        "是否凌晨 0-5 点"),
        ("txn_1h_count",        "1 小时内该用户交易笔数"),
        ("txn_1h_amount",       "1 小时内交易总额"),
        ("txn_city_match",      "交易城市≠常用城市"),
        ("txn_geo_risk",        "IP 代理/Tor/黑名单"),
        ("txn_to_card_black",   "收款卡在黑名单"),
        ("txn_1h_into_count",   "1h 内转入同卡的不同付款卡数"),
        ("txn_device_user_count", "交易设备关联用户数"),
    ]
    login_feats = [
        ("login_success",          "本次登录是否成功"),
        ("login_is_night",         "是否凌晨登录"),
        ("login_1h_count",         "1 小时内登录次数"),
        ("login_city_match",       "登录城市≠常用城市"),
        ("login_geo_risk",         "登录 IP 代理/Tor"),
        ("login_device_new",       "设备首次出现<7天"),
        ("login_device_user_count", "登录设备关联用户数"),
    ]
    loan_feats = [
        ("loan_amount",             "申请金额"),
        ("loan_term_months",        "期限(月)"),
        ("loan_debt_ratio",         "负债率"),
        ("loan_monthly_income",     "月收入"),
        ("loan_month_count",        "当月申请数"),
        ("loan_3m_count",           "近 3 个月申请数"),
        ("loan_apply_gap_days",     "距上次申请天数"),
        ("loan_amount_income_ratio", "申请额/月收入"),
        ("loan_geo_risk",           "申请 IP 代理/Tor"),
    ]
    card_feats = [
        ("card_amount",          "本次消费金额"),
        ("card_is_night",        "是否凌晨消费"),
        ("card_credit_limit",    "授信额度"),
        ("card_utilization",     "额度使用率(近7天)"),
        ("card_7d_txn_count",    "近 7 天交易笔数"),
        ("card_7d_txn_amount",   "近 7 天交易总额"),
        ("card_geo_count_7d",    "近 7 天不同城市数"),
        ("card_device_new",      "近 7 天出现新设备"),
    ]
    all_groups = [
        ("用户 (15)", user_feats), ("转账 (9)", txn_feats),
        ("登录 (7)", login_feats), ("贷款 (9)", loan_feats),
        ("信用卡 (8)", card_feats),
    ]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
    print("=" * 60)
