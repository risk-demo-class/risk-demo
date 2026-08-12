"""银行版 25 维特征工程。

特征契约保持与 XGBoost 的 FEATURE_COLUMNS 一致，业务语义改为客户、交易/申请、设备/IP。
"""
from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (
    BankUserInfo, BankTransaction, LoanApplication, LoginLog,
    DeviceFingerprint, IpGeoLocation,
)


def _value(value) -> float:
    return float(value or 0)


async def _count(db, model, *conditions) -> float:
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(*conditions)
    return _value((await db.execute(stmt)).scalar())


async def _sum(db, column, *conditions) -> float:
    stmt = select(func.coalesce(func.sum(column), 0)).select_from(column.table)
    if conditions:
        stmt = stmt.where(*conditions)
    return _value((await db.execute(stmt)).scalar())


async def _current_context(db: AsyncSession, source_id: str):
    txn = (await db.execute(select(BankTransaction).where(BankTransaction.txn_id == source_id))).scalar_one_or_none()
    if txn:
        return {"amount": _value(txn.amount), "time": txn.txn_time, "device_id": txn.device_id, "ip": txn.ip, "category": txn.channel}
    loan = (await db.execute(select(LoanApplication).where(LoanApplication.loan_id == source_id))).scalar_one_or_none()
    if loan:
        return {"amount": _value(loan.amount), "time": loan.application_at, "device_id": None, "ip": None, "category": loan.purpose}
    login = (await db.execute(select(LoginLog).where(LoginLog.login_id == source_id))).scalar_one_or_none()
    if login:
        return {"amount": 0.0, "time": login.login_at, "device_id": login.device_id, "ip": login.ip, "category": login.login_channel}
    return {"amount": 0.0, "time": datetime.now(), "device_id": None, "ip": None, "category": "未知"}


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    now = datetime.now()
    total_orders = await _count(db, BankTransaction, BankTransaction.user_id == user_id)
    total_amount = await _sum(db, BankTransaction.amount, BankTransaction.user_id == user_id)
    avg_amount = total_amount / total_orders if total_orders else 0.0
    max_stmt = select(func.coalesce(func.max(BankTransaction.amount), 0)).where(BankTransaction.user_id == user_id)
    max_amount = _value((await db.execute(max_stmt)).scalar())
    orders_30d = await _count(db, BankTransaction, BankTransaction.user_id == user_id, BankTransaction.txn_time >= now - timedelta(days=30))
    orders_7d = await _count(db, BankTransaction, BankTransaction.user_id == user_id, BankTransaction.txn_time >= now - timedelta(days=7))
    cancel_count = await _count(db, BankTransaction, BankTransaction.user_id == user_id, BankTransaction.txn_status.in_(["失败", "取消", "拒绝"]))
    complaint_count = await _count(db, LoginLog, LoginLog.user_id == user_id, LoginLog.success == 0)
    device_count = await _count(db, DeviceFingerprint, DeviceFingerprint.user_id == user_id)
    province_stmt = select(func.count(func.distinct(IpGeoLocation.province))).select_from(IpGeoLocation).join(LoginLog, LoginLog.ip == IpGeoLocation.ip).where(LoginLog.user_id == user_id)
    province_count = _value((await db.execute(province_stmt)).scalar())
    loan_count = await _count(db, LoanApplication, LoanApplication.user_id == user_id)
    return {
        "user_total_orders": total_orders,
        "user_orders_30d": orders_30d,
        "user_orders_7d": orders_7d,
        "user_total_amount": total_amount,
        "user_avg_order_amount": round(avg_amount, 2),
        "user_max_order_amount": max_amount,
        "user_refund_count": cancel_count,
        "user_postsale_count": loan_count,
        "user_refund_rate": cancel_count / total_orders if total_orders else 0.0,
        "user_postsale_rate": loan_count / total_orders if total_orders else 0.0,
        "user_refund_amount": 0.0,
        "user_cancel_count": cancel_count,
        "user_complaint_count": complaint_count,
        "user_address_count": device_count,
        "_bank_province_count": province_count,
    }


async def compute_order_features(db: AsyncSession, source_id: str) -> dict[str, float]:
    ctx = await _current_context(db, source_id)
    amount = ctx["amount"]
    source_time = ctx["time"]
    if source_time.tzinfo:
        hour = source_time.hour
    else:
        hour = source_time.hour
    if ctx["device_id"]:
        recent = await _count(db, BankTransaction, BankTransaction.device_id == ctx["device_id"], BankTransaction.txn_time >= source_time - timedelta(hours=1), BankTransaction.txn_time <= source_time)
        linked = await _count(db, DeviceFingerprint, DeviceFingerprint.device_id == ctx["device_id"])
    else:
        recent = 0.0
        linked = 0.0
    return {
        "order_total_amount": amount,
        "order_item_count": linked,
        "order_sku_count": recent,
        "order_discount_amount": 0.0,
        "order_discount_rate": 0.0,
        "order_pay_interval_sec": 0.0,
        "order_is_night": 1.0 if hour < 6 else 0.0,
        "order_category_count": 1.0 if ctx["category"] else 0.0,
        "_bank_device_id": ctx["device_id"],
        "_bank_ip": ctx["ip"],
        "_bank_time": source_time,
    }


async def compute_address_features(db: AsyncSession, user_id: str, source_id: str | None = None) -> dict[str, float]:
    current = await _current_context(db, source_id) if source_id else {"device_id": None, "ip": None}
    device_count = await _count(db, DeviceFingerprint, DeviceFingerprint.user_id == user_id)
    province_stmt = select(func.count(func.distinct(IpGeoLocation.province))).select_from(IpGeoLocation).join(LoginLog, LoginLog.ip == IpGeoLocation.ip).where(LoginLog.user_id == user_id)
    province_count = _value((await db.execute(province_stmt)).scalar())
    is_new = 0.0
    if current.get("device_id"):
        first_seen = (await db.execute(select(func.min(DeviceFingerprint.first_seen)).where(
            DeviceFingerprint.user_id == user_id,
            DeviceFingerprint.device_id == current["device_id"],
        ))).scalar()
        is_new = 1.0 if first_seen and first_seen >= datetime.now() - timedelta(days=7) else 0.0
    return {"addr_total_count": device_count, "addr_province_count": province_count, "addr_is_new": is_new}


async def compute_all_features(db: AsyncSession, user_id: str, order_id: str | None = None, receive_id: str | None = None) -> dict[str, float]:
    user = await compute_user_features(db, user_id)
    current = await compute_order_features(db, order_id) if order_id else {
        "order_total_amount": 0.0, "order_item_count": 0.0, "order_sku_count": 0.0,
        "order_discount_amount": 0.0, "order_discount_rate": 0.0,
        "order_pay_interval_sec": 0.0, "order_is_night": 0.0, "order_category_count": 0.0,
    }
    address = await compute_address_features(db, user_id, order_id)
    features = {**user, **current, **address}
    features.pop("_bank_province_count", None)
    for key in list(features):
        if key.startswith("_"):
            features.pop(key)
    return features


if __name__ == "__main__":
    from app.engine.ml_model import FEATURE_COLUMNS
    print("银行版特征数量:", len(FEATURE_COLUMNS))
    print("\n".join(f"{i:>2}. {name}" for i, name in enumerate(FEATURE_COLUMNS, 1)))


