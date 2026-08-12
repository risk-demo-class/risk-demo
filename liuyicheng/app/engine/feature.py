"""银行行业 25 维特征工程。

三大特征族保持基线接口思想：
- compute_user_features: 客户历史画像（10维）
- compute_order_features: 当前银行事件画像（10维，名称保留用于兼容核心引擎）
- compute_address_features: 关联卡/设备/贷款上下文（5维）
"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankCard,
    BankTransaction,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    UserInfo,
)


async def _scalar(db: AsyncSession, stmt, default: float = 0.0) -> float:
    value = (await db.execute(stmt)).scalar()
    return float(value if value is not None else default)


async def _load_event(db: AsyncSession, event_type: str, source_id: str) -> Any:
    model_and_key = {
        "信用卡": (BankTransaction, BankTransaction.txn_id),
        "转账": (BankTransaction, BankTransaction.txn_id),
        "贷款": (LoanApplication, LoanApplication.loan_id),
        "登录": (LoginLog, LoginLog.login_id),
    }
    model, key = model_and_key[event_type]
    return (await db.execute(select(model).where(key == source_id))).scalar_one()


def _event_time(event_type: str, event: Any) -> datetime:
    if event_type in ("信用卡", "转账"):
        return event.txn_at
    if event_type == "贷款":
        return event.apply_at
    return event.login_at


def _event_device(event: Any) -> str:
    return getattr(event, "device_id", "") or ""


def _event_ip(event: Any) -> str:
    return getattr(event, "ip", "") or ""


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算客户/KYC/交易/信贷历史 10 维特征。"""
    user = (await db.execute(
        select(UserInfo).where(UserInfo.user_id == user_id)
    )).scalar_one()
    now = datetime.now()
    since_30d = now - timedelta(days=30)
    since_24h = now - timedelta(hours=24)

    txn_count_stmt = select(func.count()).select_from(BankTransaction).where(
        BankTransaction.user_id == user_id,
        BankTransaction.txn_at >= since_30d,
    )
    txn_amount_stmt = select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
        BankTransaction.user_id == user_id,
        BankTransaction.txn_at >= since_30d,
    )
    failed_login_stmt = select(func.count()).select_from(LoginLog).where(
        LoginLog.user_id == user_id,
        LoginLog.login_at >= since_24h,
        LoginLog.success == 0,
    )
    loan_count_stmt = select(func.count()).select_from(LoanApplication).where(
        LoanApplication.user_id == user_id,
        LoanApplication.apply_at >= since_30d,
    )
    debt_ratio_stmt = select(func.coalesce(func.avg(LoanApplication.debt_ratio), 0)).where(
        LoanApplication.user_id == user_id,
    )
    institution_stmt = select(func.count(func.distinct(LoanApplication.institution_code))).where(
        LoanApplication.user_id == user_id,
        LoanApplication.apply_at >= since_30d,
    )

    return {
        "user_credit_score": float(user.credit_score),
        "user_account_age_days": float(max((now - user.register_at).days, 0)),
        "user_kyc_level": float(user.kyc_level),
        "user_card_count": await _scalar(
            db, select(func.count()).select_from(BankCard).where(BankCard.user_id == user_id)
        ),
        "user_transaction_count_30d": await _scalar(db, txn_count_stmt),
        "user_transaction_amount_30d": await _scalar(db, txn_amount_stmt),
        "user_failed_login_count_24h": await _scalar(db, failed_login_stmt),
        "user_loan_application_count_30d": await _scalar(db, loan_count_stmt),
        "user_avg_debt_ratio": round(await _scalar(db, debt_ratio_stmt), 4),
        "user_loan_institution_count_30d": await _scalar(db, institution_stmt),
    }


async def compute_order_features(
    db: AsyncSession,
    source_id: str,
    event_type: str,
    event: Any | None = None,
) -> dict[str, float]:
    """计算当前信用卡/贷款/转账/登录事件 10 维特征。"""
    event = event or await _load_event(db, event_type, source_id)
    event_at = _event_time(event_type, event)
    device_id = _event_device(event)
    ip = _event_ip(event)
    amount = float(getattr(event, "amount", 0) or 0)

    device = None
    if device_id:
        device = (await db.execute(
            select(DeviceFingerprint)
            .where(
                DeviceFingerprint.device_id == device_id,
                DeviceFingerprint.user_id == event.user_id,
            )
            .order_by(DeviceFingerprint.first_seen.asc())
        )).scalars().first()
    device_age = max((event_at - device.first_seen).days, 0) if device else 0
    is_new_device = 1.0 if not device or device_age < 7 else 0.0

    ip_info = None
    if ip:
        ip_info = (await db.execute(
            select(IpGeoLocation).where(IpGeoLocation.ip == ip)
        )).scalar_one_or_none()

    user_city = (await db.execute(
        select(UserInfo.home_city).where(UserInfo.user_id == event.user_id)
    )).scalar_one()
    event_geo = getattr(event, "geo", "") or ""
    lower = event_at - timedelta(hours=1)
    upper = event_at + timedelta(hours=1)

    velocity = 0.0
    distinct_cards = 0.0
    if event_type in ("信用卡", "转账"):
        velocity = await _scalar(
            db,
            select(func.count()).select_from(BankTransaction).where(
                BankTransaction.user_id == event.user_id,
                BankTransaction.txn_at.between(lower, upper),
            ),
        )
        if event.to_card:
            distinct_cards = await _scalar(
                db,
                select(func.count(func.distinct(BankTransaction.from_card))).where(
                    BankTransaction.to_card == event.to_card,
                    BankTransaction.txn_at.between(lower, upper),
                ),
            )
    elif event_type == "贷款":
        velocity = await _scalar(
            db,
            select(func.count()).select_from(LoanApplication).where(
                LoanApplication.user_id == event.user_id,
                LoanApplication.apply_at.between(lower, upper),
            ),
        )
    else:
        velocity = await _scalar(
            db,
            select(func.count()).select_from(LoginLog).where(
                LoginLog.user_id == event.user_id,
                LoginLog.login_at.between(lower, upper),
            ),
        )

    return {
        "event_amount": amount,
        "event_is_night": 1.0 if 0 <= event_at.hour < 6 else 0.0,
        "event_hour": float(event_at.hour),
        "event_is_new_device": is_new_device,
        "event_device_age_days": float(device_age),
        "event_ip_is_proxy": float(ip_info.is_proxy if ip_info else 0),
        "event_ip_is_tor": float(ip_info.is_tor if ip_info else 0),
        "event_geo_mismatch": 1.0 if event_geo and event_geo != user_city else 0.0,
        "event_velocity_1h": velocity,
        "event_distinct_source_cards_1h": distinct_cards,
    }


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    source_id: str,
    event_type: str,
    event: Any | None = None,
) -> dict[str, float]:
    """计算卡片、贷款、登录与设备关系 5 维上下文特征。"""
    event = event or await _load_event(db, event_type, source_id)
    device_id = _event_device(event)

    utilization = 0.0
    if event_type in ("信用卡", "转账"):
        card = (await db.execute(
            select(BankCard).where(BankCard.card_id == event.from_card)
        )).scalar_one_or_none()
        if card and float(card.credit_limit or 0) > 0:
            utilization = round(
                (float(card.current_balance or 0) + float(event.amount or 0))
                / float(card.credit_limit),
                4,
            )

    loan_ratio = 0.0
    if event_type == "贷款" and float(event.monthly_income or 0) > 0:
        loan_ratio = round(float(event.amount) / float(event.monthly_income), 4)

    failure_streak = 0.0
    if event_type == "登录":
        lower = event.login_at - timedelta(hours=1)
        upper = event.login_at + timedelta(hours=1)
        failure_streak = await _scalar(
            db,
            select(func.count()).select_from(LoginLog).where(
                LoginLog.user_id == user_id,
                LoginLog.success == 0,
                LoginLog.login_at.between(lower, upper),
            ),
        )

    shared_users = 0.0
    if device_id:
        shared_users = await _scalar(
            db,
            select(func.count(func.distinct(DeviceFingerprint.user_id))).where(
                DeviceFingerprint.device_id == device_id
            ),
        )

    to_card_blacklisted = 0.0
    to_card = getattr(event, "to_card", None)
    if to_card:
        # 外部名单按不可逆卡号哈希匹配；业务流水只保存内部 card_id。
        to_card_value = (await db.execute(
            select(BankCard.card_no_hash).where(BankCard.card_id == to_card)
        )).scalar_one_or_none() or to_card
        now = datetime.now()
        count_stmt = select(func.count()).select_from(BlacklistExtra).where(
            BlacklistExtra.entry_type == "银行卡号",
            BlacklistExtra.entry_value == to_card_value,
            (BlacklistExtra.expire_at.is_(None)) | (BlacklistExtra.expire_at > now),
        )
        to_card_blacklisted = 1.0 if await _scalar(db, count_stmt) > 0 else 0.0

    return {
        "context_card_credit_utilization": utilization,
        "context_loan_amount_income_ratio": loan_ratio,
        "context_login_failure_streak": failure_streak,
        "context_shared_device_user_count": shared_users,
        "context_to_card_blacklisted": to_card_blacklisted,
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    source_id: str,
    event_type: str,
) -> dict[str, float]:
    """一次读取当前事件，合并三大特征族并强制校验 25 维契约。"""
    event = await _load_event(db, event_type, source_id)
    features = await compute_user_features(db, user_id)
    features.update(await compute_order_features(db, source_id, event_type, event))
    features.update(await compute_address_features(db, user_id, source_id, event_type, event))
    if len(features) != 25:
        raise RuntimeError(f"银行特征契约应为25维，实际为{len(features)}维")
    return features
