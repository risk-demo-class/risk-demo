"""
物流风控特征工程: 3 大特征族, 共 30 维.

  compute_sender_features   寄件人族 (20 维)   -> sender_*
  compute_waybill_features  运单族 (6 维)      -> waybill_*
  compute_address_features  地址族 (4 维)      -> address_*

覆盖业务说明里的关键场景:
  高频寄件 / 凌晨揽收 / 危险品 / 跨境 / COD拒收 / 地址异常 / 实名异常
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    LogisticsAbnormalRecord,
    LogisticsAddress,
    LogisticsClaim,
    LogisticsCodSettlement,
    LogisticsComplaint,
    LogisticsCustomerAccount,
    LogisticsSender,
    LogisticsWaybill,
)


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


async def _count_since(model, db: AsyncSession, days: int, **filters) -> float:
    since = datetime.now() - timedelta(days=days)
    stmt = select(func.count()).select_from(model).where(model.create_time >= since)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _count_where(db: AsyncSession, user_id: str, condition) -> float:
    stmt = select(func.count()).select_from(LogisticsWaybill).where(
        LogisticsWaybill.sender_id == user_id,
        condition,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _avg(db: AsyncSession, user_id: str, column) -> float:
    stmt = select(func.coalesce(func.avg(column), 0)).select_from(LogisticsWaybill).where(
        LogisticsWaybill.sender_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 特征族 1: 寄件人 (20 维)
# ============================================================
async def compute_sender_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """寄件人维度聚合特征: 寄件量/实名/危险品/COD/投诉/理赔/跨境/地址异常."""
    sender = (await db.execute(
        select(LogisticsSender).where(LogisticsSender.sender_id == user_id)
    )).scalar_one_or_none()

    total = await _count(LogisticsWaybill, db, sender_id=user_id)
    total_30d = await _count_since(LogisticsWaybill, db, 30, sender_id=user_id)
    total_7d = await _count_since(LogisticsWaybill, db, 7, sender_id=user_id)
    total_weight = await _sum(LogisticsWaybill, "weight_kg", db, sender_id=user_id)
    total_value = await _sum(LogisticsWaybill, "declared_value", db, sender_id=user_id)

    night_count = float((await db.execute(
        select(func.count()).select_from(LogisticsWaybill).where(
            LogisticsWaybill.sender_id == user_id,
            func.hour(LogisticsWaybill.pickup_time) < 6,
        )
    )).scalar() or 0)
    dangerous_count = float((await db.execute(
        select(func.count()).select_from(LogisticsWaybill).where(
            LogisticsWaybill.sender_id == user_id,
            LogisticsWaybill.item_category.in_(["电池", "化学品"]),
        )
    )).scalar() or 0)

    cod_total = await _sum(LogisticsWaybill, "cod_amount", db, sender_id=user_id)
    cod_reject = float((await db.execute(
        select(func.count())
        .select_from(LogisticsCodSettlement)
        .join(LogisticsWaybill, LogisticsWaybill.waybill_no == LogisticsCodSettlement.waybill_no)
        .where(
            LogisticsWaybill.sender_id == user_id,
            LogisticsCodSettlement.collect_status == "拒收",
        )
    )).scalar() or 0)
    cod_total_count = float((await db.execute(
        select(func.count())
        .select_from(LogisticsCodSettlement)
        .join(LogisticsWaybill, LogisticsWaybill.waybill_no == LogisticsCodSettlement.waybill_no)
        .where(LogisticsWaybill.sender_id == user_id)
    )).scalar() or 0)
    cod_reject_rate = round(cod_reject / cod_total_count, 4) if cod_total_count else 0.0

    async def _join_count(model) -> float:
        return float((await db.execute(
            select(func.count())
            .select_from(model)
            .join(LogisticsWaybill, LogisticsWaybill.waybill_no == model.waybill_no)
            .where(LogisticsWaybill.sender_id == user_id)
        )).scalar() or 0)

    complaint_count = await _join_count(LogisticsComplaint)
    claim_count = await _join_count(LogisticsClaim)
    abnormal_count = await _join_count(LogisticsAbnormalRecord)
    cross_count = await _count(LogisticsWaybill, db, sender_id=user_id, is_cross_border=1)

    remote_count = float((await db.execute(
        select(func.count(func.distinct(LogisticsWaybill.address_id)))
        .select_from(LogisticsWaybill)
        .join(LogisticsAddress, LogisticsAddress.address_id == LogisticsWaybill.address_id)
        .where(LogisticsWaybill.sender_id == user_id, LogisticsAddress.is_remote == 1)
    )).scalar() or 0)
    temp_count = float((await db.execute(
        select(func.count(func.distinct(LogisticsWaybill.address_id)))
        .select_from(LogisticsWaybill)
        .join(LogisticsAddress, LogisticsAddress.address_id == LogisticsWaybill.address_id)
        .where(LogisticsWaybill.sender_id == user_id, LogisticsAddress.is_temp == 1)
    )).scalar() or 0)

    shared_keys = (
        select(
            LogisticsAddress.address_key,
            func.count(func.distinct(LogisticsAddress.recipient_id)).label("rcnt"),
        )
        .group_by(LogisticsAddress.address_key)
        .having(func.count(func.distinct(LogisticsAddress.recipient_id)) > 1)
        .subquery()
    )
    shared_count = float((await db.execute(
        select(func.count(func.distinct(LogisticsWaybill.address_id)))
        .select_from(LogisticsWaybill)
        .join(LogisticsAddress, LogisticsAddress.address_id == LogisticsWaybill.address_id)
        .join(shared_keys, LogisticsAddress.address_key == shared_keys.c.address_key)
        .where(LogisticsWaybill.sender_id == user_id)
    )).scalar() or 0)

    insured_count = await _count_where(db, user_id, LogisticsWaybill.insured_amount > 0)
    high_value_count = await _count_where(db, user_id, LogisticsWaybill.declared_value >= 1000)

    account_risk = 0.0
    if sender and sender.account_id:
        account = (await db.execute(
            select(LogisticsCustomerAccount).where(
                LogisticsCustomerAccount.account_id == sender.account_id
            )
        )).scalar_one_or_none()
        if account and (account.credit_level == "高风险" or account.status == "冻结"):
            account_risk = 1.0

    return {
        "sender_total_waybills": total,
        "sender_waybills_30d": total_30d,
        "sender_waybills_7d": total_7d,
        "sender_night_pickup_count": night_count,
        "sender_dangerous_item_count": dangerous_count,
        "sender_cod_total_amount": round(cod_total, 2),
        "sender_cod_reject_rate": cod_reject_rate,
        "sender_realname_verified": float(sender.is_real_name_verified) if sender else 0.0,
        "sender_verify_fail_count": float(sender.verify_fail_count) if sender else 0.0,
        "sender_complaint_count": complaint_count,
        "sender_claim_count": claim_count,
        "sender_abnormal_count": abnormal_count,
        "sender_cross_border_count": cross_count,
        "sender_remote_address_count": remote_count,
        "sender_temp_address_count": temp_count,
        "sender_shared_address_count": shared_count,
        "sender_insured_ratio": round(insured_count / total, 4) if total else 0.0,
        "sender_high_value_ratio": round(high_value_count / total, 4) if total else 0.0,
        "sender_value_weight_ratio": round(total_value / total_weight, 4) if total_weight else 0.0,
        "sender_account_risk": account_risk,
    }


# ============================================================
# 特征族 2: 运单 (6 维)
# ============================================================
async def compute_waybill_features(
    db: AsyncSession,
    user_id: str,
    waybill_no: str | None = None,
) -> dict[str, float]:
    """当前运单维度特征: 申报价值/重量/危险品/跨境/状态风险."""
    zeros = {
        "waybill_declared_value": 0.0,
        "waybill_weight_kg": 0.0,
        "waybill_value_weight_ratio": 0.0,
        "waybill_is_dangerous": 0.0,
        "waybill_is_cross_border": 0.0,
        "waybill_status_risk": 0.0,
    }
    if not waybill_no:
        return zeros
    waybill = (await db.execute(
        select(LogisticsWaybill).where(
            LogisticsWaybill.waybill_no == waybill_no,
            LogisticsWaybill.sender_id == user_id,
        )
    )).scalar_one_or_none()
    if not waybill:
        return zeros

    declared = float(waybill.declared_value or 0)
    weight = float(waybill.weight_kg or 0)
    return {
        "waybill_declared_value": declared,
        "waybill_weight_kg": weight,
        "waybill_value_weight_ratio": round(declared / weight, 4) if weight else 0.0,
        "waybill_is_dangerous": 1.0 if waybill.item_category in ("电池", "化学品") else 0.0,
        "waybill_is_cross_border": float(waybill.is_cross_border or 0),
        "waybill_status_risk": 1.0 if waybill.status in ("拒收", "退回", "异常") else 0.0,
    }


# ============================================================
# 特征族 3: 地址 (4 维)
# ============================================================
async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    address_id: str | None = None,
) -> dict[str, float]:
    """收件地址维度特征: 偏远/临时/共用/使用频次."""
    zeros = {
        "address_is_remote": 0.0,
        "address_is_temp": 0.0,
        "address_shared_count": 0.0,
        "address_use_count": 0.0,
    }
    if not address_id:
        return zeros
    address = (await db.execute(
        select(LogisticsAddress).where(LogisticsAddress.address_id == address_id)
    )).scalar_one_or_none()
    if not address:
        return zeros

    shared_count = float((await db.execute(
        select(func.count(func.distinct(LogisticsAddress.recipient_id))).where(
            LogisticsAddress.address_key == address.address_key
        )
    )).scalar() or 0)
    return {
        "address_is_remote": float(address.is_remote or 0),
        "address_is_temp": float(address.is_temp or 0),
        "address_shared_count": shared_count,
        "address_use_count": float(address.use_count or 0),
    }


# ============================================================
# 汇总入口
# ============================================================
async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    waybill_no: str | None = None,
    address_id: str | None = None,
) -> dict[str, float]:
    """三大特征族合并, 共 30 维."""
    features = await compute_sender_features(db, user_id)
    features.update(await compute_waybill_features(db, user_id, waybill_no))
    features.update(await compute_address_features(db, user_id, address_id))
    return features
