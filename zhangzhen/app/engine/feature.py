"""固定 25 维银行风险特征。

特征顺序是规则、模型、页面和测试之间的硬契约，不能随意调整。
所有时间窗口都以业务事件发生时间为上限，禁止读取未来数据。
"""

from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import (
    BankTransaction,
    DeviceFingerprint,
    LoanApplication,
    LoginLog,
    TransactionStatus,
)
from app.service.context import RiskContext


FEATURE_COLUMNS: tuple[str, ...] = (
    "user_account_age_days",
    "user_credit_score",
    "user_kyc_level",
    "user_txn_count_30d",
    "user_txn_amount_30d",
    "user_avg_txn_amount_30d",
    "user_failed_login_count_24h",
    "txn_amount",
    "txn_amount_vs_avg_ratio",
    "txn_count_1h",
    "txn_amount_24h",
    "txn_is_night",
    "txn_is_new_beneficiary",
    "txn_cross_city",
    "txn_beneficiary_payer_count_1h",
    "device_age_days",
    "device_user_count_30d",
    "device_is_new",
    "ip_is_proxy",
    "ip_is_tor",
    "login_geo_jump_km",
    "loan_amount",
    "loan_debt_ratio",
    "loan_institution_count_30d",
    "card_utilization_rate",
)


KYC_NUMERIC = {"L1": 1.0, "L2": 2.0, "L3": 3.0}
COUNTED_TRANSACTION_STATUSES = (TransactionStatus.PENDING, TransactionStatus.SUCCESS)

# 教学版城市中心点。无法识别的城市返回 0，不伪造距离。
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "成都": (30.5728, 104.0668),
    "武汉": (30.5928, 114.3055),
    "西安": (34.3416, 108.9398),
    "南京": (32.0603, 118.7969),
}


def _days_between(later, earlier) -> float:
    return float(max((later - earlier).days, 0))


def _haversine_km(city_a: str | None, city_b: str | None) -> float:
    if not city_a or not city_b or city_a == city_b:
        return 0.0
    point_a = CITY_COORDINATES.get(city_a)
    point_b = CITY_COORDINATES.get(city_b)
    if point_a is None or point_b is None:
        return 0.0
    lat1, lon1 = map(radians, point_a)
    lat2, lon2 = map(radians, point_b)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return round(6371.0 * 2 * asin(sqrt(value)), 2)


async def _transaction_aggregates(db: AsyncSession, context: RiskContext) -> tuple[int, float, float]:
    start_30d = context.event_time - timedelta(days=30)
    result = await db.execute(
        select(
            func.count(BankTransaction.txn_id),
            func.coalesce(func.sum(BankTransaction.amount), 0),
        ).where(
            BankTransaction.user_id == context.request.user_id,
            BankTransaction.txn_time >= start_30d,
            BankTransaction.txn_time <= context.event_time,
            BankTransaction.status.in_(COUNTED_TRANSACTION_STATUSES),
        )
    )
    count, amount = result.one()
    count_value = int(count or 0)
    amount_value = float(amount or 0)
    average = amount_value / count_value if count_value else 0.0
    return count_value, amount_value, average


async def _failed_login_count(db: AsyncSession, context: RiskContext) -> int:
    result = await db.execute(
        select(func.count(LoginLog.login_id)).where(
            LoginLog.user_id == context.request.user_id,
            LoginLog.success.is_(False),
            LoginLog.login_at >= context.event_time - timedelta(hours=24),
            LoginLog.login_at <= context.event_time,
        )
    )
    return int(result.scalar_one() or 0)


async def _transaction_window_features(
    db: AsyncSession,
    context: RiskContext,
) -> tuple[int, float, float, int]:
    if context.transaction is None:
        return 0, 0.0, 0.0, 0

    transaction = context.transaction
    result = await db.execute(
        select(
            func.count(BankTransaction.txn_id),
            func.coalesce(func.sum(BankTransaction.amount), 0),
        ).where(
            BankTransaction.user_id == context.request.user_id,
            BankTransaction.txn_time >= context.event_time - timedelta(hours=1),
            BankTransaction.txn_time <= context.event_time,
            BankTransaction.status.in_(COUNTED_TRANSACTION_STATUSES),
        )
    )
    count_1h, _ = result.one()

    amount_result = await db.execute(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            BankTransaction.user_id == context.request.user_id,
            BankTransaction.txn_time >= context.event_time - timedelta(hours=24),
            BankTransaction.txn_time <= context.event_time,
            BankTransaction.status.in_(COUNTED_TRANSACTION_STATUSES),
        )
    )
    amount_24h = float(amount_result.scalar_one() or 0)

    is_new_beneficiary = 0.0
    payer_count = 0
    if transaction.beneficiary_account_hash:
        history_result = await db.execute(
            select(func.count(BankTransaction.txn_id)).where(
                BankTransaction.user_id == context.request.user_id,
                BankTransaction.beneficiary_account_hash == transaction.beneficiary_account_hash,
                BankTransaction.txn_time < context.event_time,
                BankTransaction.status.in_(COUNTED_TRANSACTION_STATUSES),
            )
        )
        is_new_beneficiary = 1.0 if int(history_result.scalar_one() or 0) == 0 else 0.0

        payer_result = await db.execute(
            select(func.count(distinct(BankTransaction.from_account_id))).where(
                BankTransaction.beneficiary_account_hash == transaction.beneficiary_account_hash,
                BankTransaction.from_account_id.is_not(None),
                BankTransaction.txn_time >= context.event_time - timedelta(hours=1),
                BankTransaction.txn_time <= context.event_time,
                BankTransaction.status.in_(COUNTED_TRANSACTION_STATUSES),
            )
        )
        payer_count = int(payer_result.scalar_one() or 0)

    return int(count_1h or 0), amount_24h, is_new_beneficiary, payer_count


async def _device_user_count(db: AsyncSession, context: RiskContext) -> int:
    if not context.device_id:
        return 0
    result = await db.execute(
        select(func.count(distinct(DeviceFingerprint.user_id))).where(
            DeviceFingerprint.device_id == context.device_id,
            DeviceFingerprint.last_seen >= context.event_time - timedelta(days=30),
            DeviceFingerprint.first_seen <= context.event_time,
        )
    )
    return int(result.scalar_one() or 0)


async def _previous_login_distance(db: AsyncSession, context: RiskContext) -> float:
    result = await db.execute(
        select(LoginLog.geo)
        .where(
            LoginLog.user_id == context.request.user_id,
            LoginLog.success.is_(True),
            LoginLog.login_at < context.event_time,
        )
        .order_by(LoginLog.login_at.desc())
        .limit(1)
    )
    previous_geo = result.scalar_one_or_none()
    return _haversine_km(previous_geo, context.geo)


async def _loan_institution_count(db: AsyncSession, context: RiskContext) -> int:
    if context.loan is None:
        return 0
    result = await db.execute(
        select(func.count(distinct(LoanApplication.institution_code))).where(
            LoanApplication.user_id == context.request.user_id,
            LoanApplication.apply_at >= context.event_time - timedelta(days=30),
            LoanApplication.apply_at <= context.event_time,
        )
    )
    return int(result.scalar_one() or 0)


async def compute_features(db: AsyncSession, context: RiskContext) -> dict[str, float]:
    txn_count_30d, txn_amount_30d, avg_txn_amount_30d = await _transaction_aggregates(db, context)
    failed_login_count = await _failed_login_count(db, context)
    txn_count_1h, txn_amount_24h, is_new_beneficiary, payer_count = (
        await _transaction_window_features(db, context)
    )
    device_user_count = await _device_user_count(db, context)
    login_distance = await _previous_login_distance(db, context)
    loan_institution_count = await _loan_institution_count(db, context)

    txn_amount = float(context.transaction.amount) if context.transaction else 0.0
    amount_ratio = txn_amount / avg_txn_amount_30d if avg_txn_amount_30d else 0.0
    device_age_days = (
        _days_between(context.event_time, context.device.first_seen) if context.device else 0.0
    )
    card_utilization = 0.0
    if context.card and float(context.card.credit_limit) > 0:
        card_utilization = (
            float(context.card.credit_limit) - float(context.card.available_limit)
        ) / float(context.card.credit_limit)
        card_utilization = min(max(card_utilization, 0.0), 1.0)

    features = {
        "user_account_age_days": _days_between(context.event_time, context.customer.register_at),
        "user_credit_score": float(context.customer.credit_score),
        "user_kyc_level": KYC_NUMERIC[context.customer.kyc_level.value],
        "user_txn_count_30d": float(txn_count_30d),
        "user_txn_amount_30d": txn_amount_30d,
        "user_avg_txn_amount_30d": avg_txn_amount_30d,
        "user_failed_login_count_24h": float(failed_login_count),
        "txn_amount": txn_amount,
        "txn_amount_vs_avg_ratio": amount_ratio,
        "txn_count_1h": float(txn_count_1h),
        "txn_amount_24h": txn_amount_24h,
        "txn_is_night": float(context.event_time.hour <= 5 if context.transaction else 0),
        "txn_is_new_beneficiary": is_new_beneficiary,
        "txn_cross_city": float(
            bool(context.transaction and context.geo and context.geo != context.customer.home_city)
        ),
        "txn_beneficiary_payer_count_1h": float(payer_count),
        "device_age_days": device_age_days,
        "device_user_count_30d": float(device_user_count),
        "device_is_new": float(bool(context.device and device_age_days < 7)),
        "ip_is_proxy": float(bool(context.ip_info and context.ip_info.is_proxy)),
        "ip_is_tor": float(bool(context.ip_info and context.ip_info.is_tor)),
        "login_geo_jump_km": login_distance,
        "loan_amount": float(context.loan.amount) if context.loan else 0.0,
        "loan_debt_ratio": float(context.loan.debt_ratio) if context.loan else 0.0,
        "loan_institution_count_30d": float(loan_institution_count),
        "card_utilization_rate": card_utilization,
    }
    if tuple(features) != FEATURE_COLUMNS:
        raise RuntimeError("25维特征名称或顺序被意外修改")
    return features

