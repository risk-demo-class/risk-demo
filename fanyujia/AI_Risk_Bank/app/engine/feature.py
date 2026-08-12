"""银行风控 25 维特征工程。所有特征缺数据时返回 0，保证训练/推理列完整。"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankTransaction, DeviceFingerprint, IpGeoLocation, LoanApplication,
    LoginLog, PayeeRelationship, UserInfo,
)


async def _scalar(db: AsyncSession, stmt, default: float = 0.0) -> float:
    value = (await db.execute(stmt)).scalar()
    return float(value or default)


async def _source_context(db: AsyncSession, source_id: str | None) -> dict:
    if not source_id:
        return {}
    txn = (await db.execute(select(BankTransaction).where(BankTransaction.txn_id == source_id))).scalar_one_or_none()
    if txn:
        return {"kind": "txn", "amount": float(txn.amount), "at": txn.txn_time, "device_id": txn.device_id,
                "ip": txn.ip, "geo": txn.geo, "payee_id": txn.payee_id, "card_id": txn.from_card_id, "to_card_hash": txn.to_card_hash,
                "channel": txn.channel, "user_id": txn.user_id}
    loan = (await db.execute(select(LoanApplication).where(LoanApplication.loan_id == source_id))).scalar_one_or_none()
    if loan:
        return {"kind": "loan", "amount": float(loan.amount), "at": loan.apply_at, "device_id": loan.device_id,
                "ip": loan.ip, "geo": None, "payee_id": None, "card_id": None, "channel": "loan", "user_id": loan.user_id}
    login = (await db.execute(select(LoginLog).where(LoginLog.login_id == source_id))).scalar_one_or_none()
    if login:
        return {"kind": "login", "amount": 0.0, "at": login.login_at, "device_id": login.device_id,
                "ip": login.ip, "geo": login.geo, "payee_id": None, "card_id": None, "channel": "login", "user_id": login.user_id}
    return {}


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    now = datetime.now()
    h1, d1, d30 = now - timedelta(hours=1), now - timedelta(days=1), now - timedelta(days=30)
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one_or_none()
    txn_base = BankTransaction.user_id == user_id
    login_base = LoginLog.user_id == user_id
    device_base = DeviceFingerprint.user_id == user_id
    return {
        "user_txn_count_1h": await _scalar(db, select(func.count()).select_from(BankTransaction).where(txn_base, BankTransaction.txn_time >= h1)),
        "user_txn_count_24h": await _scalar(db, select(func.count()).select_from(BankTransaction).where(txn_base, BankTransaction.txn_time >= d1)),
        "user_txn_amount_24h": await _scalar(db, select(func.sum(BankTransaction.amount)).where(txn_base, BankTransaction.txn_time >= d1)),
        "user_avg_txn_amount_30d": await _scalar(db, select(func.avg(BankTransaction.amount)).where(txn_base, BankTransaction.txn_time >= d30)),
        "user_max_txn_amount_30d": await _scalar(db, select(func.max(BankTransaction.amount)).where(txn_base, BankTransaction.txn_time >= d30)),
        "user_login_fail_count_1h": await _scalar(db, select(func.count()).select_from(LoginLog).where(login_base, LoginLog.login_at >= h1, LoginLog.success.is_(False))),
        "user_distinct_devices_30d": await _scalar(db, select(func.count(func.distinct(DeviceFingerprint.device_id))).where(device_base, DeviceFingerprint.last_seen >= d30)),
        "user_distinct_ips_24h": await _scalar(db, select(func.count(func.distinct(BankTransaction.ip))).where(txn_base, BankTransaction.txn_time >= d1)),
        "user_new_device_flag": await _scalar(db, select(func.count()).select_from(DeviceFingerprint).where(device_base, DeviceFingerprint.first_seen >= now - timedelta(days=7))),
        "user_geo_jump": float(bool(user and user.home_geo and await _scalar(db, select(func.count()).select_from(BankTransaction).where(txn_base, BankTransaction.geo != user.home_geo, BankTransaction.txn_time >= d1)))),
        "user_credit_score": float(user.credit_score if user else 0),
        "user_debt_ratio": float(user.debt_ratio if user else 0),
        "user_loan_apply_count_30d": await _scalar(db, select(func.count()).select_from(LoanApplication).where(LoanApplication.user_id == user_id, LoanApplication.apply_at >= d30)),
        "user_account_age_days": float((now - user.register_at).days if user else 0),
    }


async def compute_order_features(db: AsyncSession, order_id: str | None) -> dict[str, float]:
    ctx = await _source_context(db, order_id)
    now = datetime.now()
    at = ctx.get("at", now)
    hour = float(at.hour) if at else 0.0
    amount = float(ctx.get("amount", 0.0))
    user_id, payee_id, card_id = ctx.get("user_id"), ctx.get("payee_id"), ctx.get("card_id")
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one_or_none() if user_id else None
    one_hour = at - timedelta(hours=1) if at else now - timedelta(hours=1)
    payee_count = 0.0
    card_count = 0.0
    is_new_payee = 0.0
    if user_id and payee_id:
        payee_count = await _scalar(db, select(func.count()).select_from(BankTransaction).where(BankTransaction.user_id == user_id, BankTransaction.payee_id == payee_id, BankTransaction.txn_time >= one_hour))
        is_new_payee = float(not bool((await db.execute(select(PayeeRelationship.relation_id).where(PayeeRelationship.user_id == user_id, PayeeRelationship.payee_id == payee_id))).scalar_one_or_none()))
    if card_id:
        card_count = await _scalar(db, select(func.count(func.distinct(BankTransaction.from_card_id))).where(BankTransaction.to_card_hash == ctx.get("to_card_hash"), BankTransaction.txn_time >= one_hour))
    channel = ctx.get("channel", "")
    return {
        "txn_amount": amount,
        "txn_hour": hour,
        "txn_is_night": float(0 <= hour < 5),
        "txn_is_cross_geo": float(bool(user and user.home_geo and ctx.get("geo") and user.home_geo != ctx.get("geo"))),
        "txn_is_new_payee": is_new_payee,
        "txn_count_to_payee_1h": payee_count,
        "txn_distinct_source_cards_1h": card_count,
        "txn_channel_risk": float(channel in {"web", "loan"}),
    }


async def compute_address_features(db: AsyncSession, user_id: str, receive_id: str | None = None) -> dict[str, float]:
    device_id = receive_id
    ctx = await _source_context(db, receive_id) if receive_id else {}
    if ctx:
        device_id = ctx.get("device_id")
    linked = 0.0
    if device_id:
        linked = await _scalar(db, select(func.count(func.distinct(DeviceFingerprint.user_id))).where(DeviceFingerprint.device_id == device_id))
    ip = ctx.get("ip") if ctx else None
    ip_row = (await db.execute(select(IpGeoLocation).where(IpGeoLocation.ip == ip))).scalar_one_or_none() if ip else None
    return {"device_linked_user_count": linked, "ip_is_proxy": float(bool(ip_row and ip_row.is_proxy)), "ip_is_tor": float(bool(ip_row and ip_row.is_tor))}


async def compute_all_features(db: AsyncSession, user_id: str, order_id: str | None = None, receive_id: str | None = None) -> dict[str, float]:
    features = await compute_user_features(db, user_id)
    features.update(await compute_order_features(db, order_id))
    ctx = await _source_context(db, order_id)
    features.update(await compute_address_features(db, user_id, ctx.get("device_id") or receive_id))
    ip = ctx.get("ip")
    if ip:
        ip_row = (await db.execute(select(IpGeoLocation).where(IpGeoLocation.ip == ip))).scalar_one_or_none()
        features["ip_is_proxy"] = float(bool(ip_row and ip_row.is_proxy))
        features["ip_is_tor"] = float(bool(ip_row and ip_row.is_tor))
    return features
