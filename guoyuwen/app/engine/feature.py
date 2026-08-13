"""银行风控 25 维特征工程。

前缀是冻结的模型 ABI：14 个 ``user_*`` 表示客户历史，8 个 ``order_*``
表示本次银行事件，3 个 ``addr_*`` 表示设备、IP 与地理环境。所有历史窗口均以
业务 source 的发生时间为截止点，不读取风险决策、规则命中、模型分或训练标签。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    BankCard,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)


USER_FEATURE_COLUMNS = [
    "user_txn_count_7d",
    "user_txn_count_30d",
    "user_total_txn_amount",
    "user_avg_txn_amount",
    "user_max_txn_amount",
    "user_bound_card_count",
    "user_failed_login_count_30d",
    "user_device_count",
    "user_loan_apply_count_30d",
    "user_loan_institution_count_30d",
    "user_max_debt_ratio",
    "user_night_operation_count_7d",
    "user_incoming_card_count_1h",
    "user_account_age_days",
]

ORDER_FEATURE_COLUMNS = [
    "order_event_amount",
    "order_txn_count_1h",
    "order_is_night",
    "order_new_device_days",
    "order_device_user_count",
    "order_payee_card_count_1h",
    "order_loan_institution_count_30d",
    "order_debt_ratio",
]

ADDRESS_FEATURE_COLUMNS = [
    "addr_is_proxy",
    "addr_is_tor",
    "addr_is_unusual",
]


class FeatureSourceError(RuntimeError):
    """已通过校验的 source 在特征阶段无法解析时抛出，禁止静默填零。"""


@dataclass(frozen=True)
class BankEventContext:
    event_type: str
    source_id: str
    user_id: str
    event_time: datetime
    amount: float = 0.0
    device_id: str | None = None
    ip: str | None = None
    geo: str | None = None
    payee_card_id: str | None = None
    debt_ratio: float = 0.0


async def _latest_login_environment(
    db: AsyncSession, user_id: str, as_of: datetime
) -> tuple[str | None, str | None, str | None]:
    """贷款/绑卡没有设备字段时，取事件前最近一次成功登录；无记录即无环境。"""
    row = (
        await db.execute(
            select(LoginLog.device_id, LoginLog.ip, LoginLog.geo)
            .where(
                LoginLog.user_id == user_id,
                LoginLog.success.is_(True),
                LoginLog.login_at <= as_of,
            )
            .order_by(LoginLog.login_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None, None
    return row.device_id, row.ip, row.geo


async def load_event_context(
    db: AsyncSession, event_type: str, source_id: str, user_id: str
) -> BankEventContext:
    """按固定事件派发表加载 source，不根据自由文本或 ID 前缀猜类型。"""
    if event_type == "登录":
        row = (
            await db.execute(
                select(
                    LoginLog.login_at,
                    LoginLog.device_id,
                    LoginLog.ip,
                    LoginLog.geo,
                ).where(LoginLog.login_id == source_id)
            )
        ).first()
        if row is not None:
            return BankEventContext(
                event_type, source_id, user_id, row.login_at,
                device_id=row.device_id, ip=row.ip, geo=row.geo,
            )

    elif event_type == "转账":
        row = (
            await db.execute(
                select(
                    Transaction.txn_at,
                    Transaction.amount,
                    Transaction.device_id,
                    Transaction.ip,
                    Transaction.geo,
                    Transaction.to_card,
                ).where(Transaction.txn_id == source_id)
            )
        ).first()
        if row is not None:
            return BankEventContext(
                event_type, source_id, user_id, row.txn_at,
                amount=float(row.amount), device_id=row.device_id, ip=row.ip,
                geo=row.geo, payee_card_id=row.to_card,
            )

    elif event_type == "贷款申请":
        row = (
            await db.execute(
                select(
                    LoanApplication.apply_at,
                    LoanApplication.amount,
                    LoanApplication.debt_ratio,
                ).where(LoanApplication.loan_id == source_id)
            )
        ).first()
        if row is not None:
            device_id, ip, geo = await _latest_login_environment(
                db, user_id, row.apply_at
            )
            return BankEventContext(
                event_type, source_id, user_id, row.apply_at,
                amount=float(row.amount), device_id=device_id, ip=ip, geo=geo,
                debt_ratio=float(row.debt_ratio),
            )

    elif event_type == "绑卡":
        row = (
            await db.execute(
                select(BankCard.bind_at).where(BankCard.card_id == source_id)
            )
        ).first()
        if row is not None:
            device_id, ip, geo = await _latest_login_environment(
                db, user_id, row.bind_at
            )
            return BankEventContext(
                event_type, source_id, user_id, row.bind_at,
                device_id=device_id, ip=ip, geo=geo,
            )
    else:
        raise FeatureSourceError(f"不支持的银行事件类型: {event_type}")

    raise FeatureSourceError(
        f"特征阶段无法加载 event_type={event_type} 的 source_id={source_id}"
    )


async def compute_user_features(
    db: AsyncSession, user_id: str, as_of: datetime | None = None
) -> dict[str, float]:
    """计算 14 个客户历史特征；当前事件不计入历史窗口。"""
    as_of = as_of or datetime.now()
    since_7d = as_of - timedelta(days=7)
    since_30d = as_of - timedelta(days=30)
    payer_card = aliased(BankCard)

    txn_row = (
        await db.execute(
            select(
                func.sum(func.if_(Transaction.txn_at >= since_7d, 1, 0)),
                func.sum(func.if_(Transaction.txn_at >= since_30d, 1, 0)),
                func.coalesce(func.sum(Transaction.amount), 0),
                func.coalesce(func.avg(Transaction.amount), 0),
                func.coalesce(func.max(Transaction.amount), 0),
            )
            .select_from(Transaction)
            .join(payer_card, Transaction.from_card == payer_card.card_id)
            .where(
                payer_card.user_id == user_id,
                Transaction.status == "成功",
                Transaction.txn_at < as_of,
            )
        )
    ).one()

    bound_card_count = (
        await db.execute(
            select(func.count())
            .select_from(BankCard)
            .where(
                BankCard.user_id == user_id,
                BankCard.is_active.is_(True),
                BankCard.bind_at < as_of,
            )
        )
    ).scalar_one()

    failed_login_count = (
        await db.execute(
            select(func.count())
            .select_from(LoginLog)
            .where(
                LoginLog.user_id == user_id,
                LoginLog.success.is_(False),
                LoginLog.login_at >= since_30d,
                LoginLog.login_at < as_of,
            )
        )
    ).scalar_one()

    device_count = (
        await db.execute(
            select(func.count(distinct(DeviceFingerprint.device_id)))
            .where(
                DeviceFingerprint.user_id == user_id,
                DeviceFingerprint.first_seen < as_of,
            )
        )
    ).scalar_one()

    loan_row = (
        await db.execute(
            select(
                func.count(),
                func.count(distinct(LoanApplication.institution_code)),
                func.coalesce(func.max(LoanApplication.debt_ratio), 0),
            )
            .select_from(LoanApplication)
            .where(
                LoanApplication.user_id == user_id,
                LoanApplication.apply_at >= since_30d,
                LoanApplication.apply_at < as_of,
            )
        )
    ).one()

    night_txn_count = (
        await db.execute(
            select(func.count())
            .select_from(Transaction)
            .join(payer_card, Transaction.from_card == payer_card.card_id)
            .where(
                payer_card.user_id == user_id,
                Transaction.txn_at >= since_7d,
                Transaction.txn_at < as_of,
                func.hour(Transaction.txn_at) < 5,
            )
        )
    ).scalar_one()
    night_login_count = (
        await db.execute(
            select(func.count())
            .select_from(LoginLog)
            .where(
                LoginLog.user_id == user_id,
                LoginLog.login_at >= since_7d,
                LoginLog.login_at < as_of,
                func.hour(LoginLog.login_at) < 5,
            )
        )
    ).scalar_one()

    payee_card = aliased(BankCard)
    incoming_card_count = (
        await db.execute(
            select(func.count(distinct(Transaction.from_card)))
            .select_from(Transaction)
            .join(payee_card, Transaction.to_card == payee_card.card_id)
            .where(
                payee_card.user_id == user_id,
                Transaction.status == "成功",
                Transaction.txn_at >= as_of - timedelta(hours=1),
                Transaction.txn_at < as_of,
            )
        )
    ).scalar_one()

    register_at = (
        await db.execute(
            select(UserInfo.register_at).where(UserInfo.user_id == user_id)
        )
    ).scalar_one_or_none()
    if register_at is None:
        raise FeatureSourceError(f"特征阶段无法加载用户: {user_id}")

    values = [
        float(txn_row[0] or 0),
        float(txn_row[1] or 0),
        float(txn_row[2] or 0),
        round(float(txn_row[3] or 0), 2),
        float(txn_row[4] or 0),
        float(bound_card_count or 0),
        float(failed_login_count or 0),
        float(device_count or 0),
        float(loan_row[0] or 0),
        float(loan_row[1] or 0),
        round(float(loan_row[2] or 0), 4),
        float((night_txn_count or 0) + (night_login_count or 0)),
        float(incoming_card_count or 0),
        float(max((as_of - register_at).days, 0)),
    ]
    return dict(zip(USER_FEATURE_COLUMNS, values, strict=True))


async def compute_order_features(
    db: AsyncSession, context: BankEventContext
) -> dict[str, float]:
    """计算 8 个本次事件特征，并为不适用维度给出显式中性语义。"""
    txn_count_1h = 0
    payee_card_count_1h = 0
    loan_institution_count_30d = 0

    if context.event_type == "转账":
        payer_card = aliased(BankCard)
        txn_count_1h = (
            await db.execute(
                select(func.count())
                .select_from(Transaction)
                .join(payer_card, Transaction.from_card == payer_card.card_id)
                .where(
                    payer_card.user_id == context.user_id,
                    Transaction.status == "成功",
                    Transaction.txn_at >= context.event_time - timedelta(hours=1),
                    Transaction.txn_at <= context.event_time,
                )
            )
        ).scalar_one()
        payee_card_count_1h = (
            await db.execute(
                select(func.count(distinct(Transaction.from_card)))
                .where(
                    Transaction.to_card == context.payee_card_id,
                    Transaction.status == "成功",
                    Transaction.txn_at >= context.event_time - timedelta(hours=1),
                    Transaction.txn_at <= context.event_time,
                )
            )
        ).scalar_one()

    if context.event_type == "贷款申请":
        loan_institution_count_30d = (
            await db.execute(
                select(func.count(distinct(LoanApplication.institution_code)))
                .where(
                    LoanApplication.user_id == context.user_id,
                    LoanApplication.apply_at >= context.event_time - timedelta(days=30),
                    LoanApplication.apply_at <= context.event_time,
                )
            )
        ).scalar_one()

    # 贷款、绑卡无设备上下文时，3650 天和 1 个关联用户分别表达“非新设备”和
    # “非共享设备”；这两个值是业务中性值，不是查询失败兜底。
    new_device_days = 3650.0
    device_user_count = 1.0
    if context.device_id:
        first_seen = (
            await db.execute(
                select(DeviceFingerprint.first_seen).where(
                    DeviceFingerprint.device_id == context.device_id,
                    DeviceFingerprint.user_id == context.user_id,
                )
            )
        ).scalar_one_or_none()
        if first_seen is None:
            raise FeatureSourceError(
                f"设备 {context.device_id} 缺少用户 {context.user_id} 的指纹关联"
            )
        new_device_days = max(
            (context.event_time - first_seen).total_seconds() / 86400, 0.0
        )
        device_user_count = float(
            (
                await db.execute(
                    select(func.count(distinct(DeviceFingerprint.user_id))).where(
                        DeviceFingerprint.device_id == context.device_id
                    )
                )
            ).scalar_one()
            or 1
        )

    values = [
        float(context.amount),
        float(txn_count_1h or 0),
        1.0 if 0 <= context.event_time.hour < 5 else 0.0,
        round(new_device_days, 4),
        device_user_count,
        float(payee_card_count_1h or 0),
        float(loan_institution_count_30d or 0),
        round(float(context.debt_ratio), 4),
    ]
    return dict(zip(ORDER_FEATURE_COLUMNS, values, strict=True))


async def compute_address_features(
    db: AsyncSession, context: BankEventContext
) -> dict[str, float]:
    """计算 3 个设备/IP/地理环境特征；无环境的贷款/绑卡使用全零中性值。"""
    if context.ip is None:
        return dict(zip(ADDRESS_FEATURE_COLUMNS, (0.0, 0.0, 0.0), strict=True))

    ip_row = (
        await db.execute(
            select(
                IpGeoLocation.is_proxy,
                IpGeoLocation.is_tor,
                IpGeoLocation.city,
            ).where(IpGeoLocation.ip == context.ip)
        )
    ).first()
    if ip_row is None:
        raise FeatureSourceError(f"IP 环境不存在: {context.ip}")

    common_city = (
        await db.execute(
            select(IpGeoLocation.city)
            .select_from(LoginLog)
            .join(IpGeoLocation, LoginLog.ip == IpGeoLocation.ip)
            .where(
                LoginLog.user_id == context.user_id,
                LoginLog.success.is_(True),
                LoginLog.login_at < context.event_time,
            )
            .group_by(IpGeoLocation.city)
            .order_by(func.count().desc(), IpGeoLocation.city.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    is_unusual = 1.0 if common_city and common_city != ip_row.city else 0.0
    return {
        "addr_is_proxy": 1.0 if ip_row.is_proxy else 0.0,
        "addr_is_tor": 1.0 if ip_row.is_tor else 0.0,
        "addr_is_unusual": is_unusual,
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    source_id: str,
    event_type: str,
) -> dict[str, float]:
    """按稳定顺序生成完整 25 维快照；任意 source 都不会缺失某个特征族。"""
    context = await load_event_context(db, event_type, source_id, user_id)
    features = await compute_user_features(db, user_id, context.event_time)
    features.update(await compute_order_features(db, context))
    features.update(await compute_address_features(db, context))
    expected = USER_FEATURE_COLUMNS + ORDER_FEATURE_COLUMNS + ADDRESS_FEATURE_COLUMNS
    if list(features) != expected:
        raise RuntimeError("银行特征顺序与 25 维 ABI 不一致")
    return features


if __name__ == "__main__":
    print("银行风控 25 维特征（14 客户历史 + 8 本次事件 + 3 环境）")
    for index, name in enumerate(
        USER_FEATURE_COLUMNS + ORDER_FEATURE_COLUMNS + ADDRESS_FEATURE_COLUMNS, 1
    ):
        print(f"{index:02d}. {name}")
