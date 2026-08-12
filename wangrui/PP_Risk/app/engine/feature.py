from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import (
    DeviceInfo,
    PaymentTransaction,
    ScreeningResult,
    UserDevice,
    UserKycReview,
    WalletAccount,
)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    account_ids = select(WalletAccount.account_id).where(
        WalletAccount.owner_type == "USER", WalletAccount.owner_id == user_id
    )
    tx_count, tx_amount = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
                PaymentTransaction.payer_account_id.in_(account_ids)
            )
        )
    ).one()
    kyc = (
        await db.execute(
            select(UserKycReview.face_score, UserKycReview.liveness_score).where(
                UserKycReview.user_id == user_id
            )
        )
    ).first()
    screening = (
        await db.execute(
            select(func.coalesce(func.max(ScreeningResult.match_score), 0)).where(
                ScreeningResult.subject_type == "USER", ScreeningResult.subject_id == user_id
            )
        )
    ).scalar_one()
    return {
        "user_transaction_count": float(tx_count),
        "user_transaction_amount": float(tx_amount),
        "user_kyc_face_score": float(kyc.face_score if kyc else 0),
        "user_kyc_liveness_score": float(kyc.liveness_score if kyc else 0),
        "user_screening_match_score": float(screening),
    }


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    transaction = (
        await db.execute(
            select(PaymentTransaction).where(PaymentTransaction.transaction_id == order_id)
        )
    ).scalar_one_or_none()
    if transaction is None:
        return {}
    created_hour = transaction.create_time.hour if transaction.create_time else 12
    return {
        "transaction_amount": float(transaction.amount or 0),
        "transaction_is_cross_border": float(transaction.transaction_type == "CROSS_BORDER"),
        "transaction_is_cash_movement": float(transaction.transaction_type in {"TOP_UP", "WITHDRAWAL"}),
        "transaction_is_night": float(created_hour < 6),
    }


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None = None
) -> dict[str, float]:
    device_count = (
        await db.execute(select(func.count()).select_from(UserDevice).where(UserDevice.user_id == user_id))
    ).scalar_one()
    device = None
    if receive_id:
        device = (
            await db.execute(select(DeviceInfo).where(DeviceInfo.device_id == receive_id))
        ).scalar_one_or_none()
    return {
        "device_count": float(device_count),
        "device_is_emulator": float(bool(device and device.is_emulator)),
        "device_is_rooted": float(bool(device and device.is_rooted)),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features

