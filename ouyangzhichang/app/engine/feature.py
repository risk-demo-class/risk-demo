"""物流风控25维特征：寄件人14 + 运单8 + 地址3。"""
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import Address, DeliveryResult, Shipment, ShipmentItem, UserInfo


async def _scalar(db, stmt, default=0.0) -> float:
    value = (await db.execute(stmt)).scalar_one_or_none()
    return float(value if value is not None else default)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    now = datetime.now()
    base = Shipment.sender_user_id == user_id
    async def count_since(days=None, hours=None, extra=None):
        since = now - (timedelta(days=days) if days is not None else timedelta(hours=hours))
        conditions = [base, Shipment.create_time >= since]
        if extra is not None:
            conditions.append(extra)
        return await _scalar(db, select(func.count()).select_from(Shipment).where(*conditions))

    total = await _scalar(db, select(func.count()).select_from(Shipment).where(base))
    cod_total = await count_since(days=90, extra=Shipment.payment_type == "货到付款")
    refused = await _scalar(
        db, select(func.count()).select_from(DeliveryResult)
        .join(Shipment, DeliveryResult.shipment_id == Shipment.shipment_id)
        .where(base, Shipment.payment_type == "货到付款",
               DeliveryResult.delivery_status == "拒收",
               DeliveryResult.delivery_time >= now - timedelta(days=90))
    )
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one_or_none()
    account_age = max((now - user.register_time).days, 0) if user else 0
    receiver_count = await _scalar(
        db, select(func.count(func.distinct(Shipment.receiver_address_id))).where(
            base, Shipment.create_time >= now - timedelta(days=30)))
    address_count = await _scalar(
        db, select(func.count(func.distinct(Shipment.sender_address_id))).where(
            base, Shipment.create_time >= now - timedelta(days=30)))
    device_users = 0.0
    if user and user.device_id:
        device_users = await _scalar(
            db, select(func.count(func.distinct(UserInfo.user_id))).where(UserInfo.device_id == user.device_id))
    dangerous_hits = await _scalar(
        db, select(func.count()).select_from(ShipmentItem)
        .join(Shipment, ShipmentItem.shipment_id == Shipment.shipment_id)
        .where(base, Shipment.create_time >= now - timedelta(days=90),
               ShipmentItem.declared_dangerous == 0,
               (ShipmentItem.battery_flag + ShipmentItem.chemical_flag + ShipmentItem.liquid_flag) > 0))
    night_count = await _scalar(
        db, select(func.count()).select_from(Shipment).where(
            base, Shipment.create_time >= now - timedelta(days=30),
            func.hour(Shipment.create_time).between(0, 5)))
    return {
        "sender_total_shipments": total,
        "sender_shipments_30d": await count_since(days=30),
        "sender_shipments_7d": await count_since(days=7),
        "sender_shipments_1h": await count_since(hours=1),
        "sender_night_shipments_30d": night_count,
        "sender_cross_border_count_90d": await count_since(days=90, extra=Shipment.is_cross_border == 1),
        "sender_dangerous_item_hits_90d": dangerous_hits,
        "sender_cod_shipments_90d": cod_total,
        "sender_cod_refuse_count_90d": refused,
        "sender_cod_refuse_rate_90d": refused / cod_total if cod_total else 0.0,
        "sender_receiver_count_30d": receiver_count,
        "sender_address_count_30d": address_count,
        "sender_device_user_count_30d": device_users,
        "sender_account_age_days": float(account_age),
    }


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """兼容固定入口；order_id在物流项目中就是shipment_id。"""
    shipment = (await db.execute(
        select(Shipment).where(Shipment.shipment_id == order_id))).scalar_one_or_none()
    if not shipment:
        return {name: 0.0 for name in (
            "shipment_actual_weight", "shipment_declared_weight_diff_rate",
            "shipment_declared_value", "shipment_item_category_count",
            "shipment_dangerous_flag", "shipment_declaration_mismatch",
            "shipment_cod_amount", "shipment_is_cross_border")}
    items = (await db.execute(
        select(ShipmentItem).where(ShipmentItem.shipment_id == order_id))).scalars().all()
    dangerous = any(i.battery_flag or i.chemical_flag or i.liquid_flag for i in items)
    mismatch = any(
        not i.declared_dangerous and (i.battery_flag or i.chemical_flag or i.liquid_flag)
        for i in items)
    declared_weight = float(shipment.declared_weight or 0)
    actual_weight = float(shipment.actual_weight or 0)
    return {
        "shipment_actual_weight": actual_weight,
        "shipment_declared_weight_diff_rate": abs(actual_weight - declared_weight) / max(declared_weight, 0.1),
        "shipment_declared_value": float(shipment.declared_value or 0),
        "shipment_item_category_count": float(len({i.item_category for i in items})),
        "shipment_dangerous_flag": float(dangerous),
        "shipment_declaration_mismatch": float(mismatch),
        "shipment_cod_amount": float(shipment.cod_amount or 0),
        "shipment_is_cross_border": float(shipment.is_cross_border or 0),
    }


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None = None,
) -> dict[str, float]:
    address = None
    if receive_id:
        address = (await db.execute(select(Address).where(Address.address_id == receive_id))).scalar_one_or_none()
    users = 0.0
    is_new = 0.0
    risky = 0.0
    if address:
        users = await _scalar(
            db, select(func.count(func.distinct(Shipment.sender_user_id))).where(
                Shipment.receiver_address_id == address.address_id,
                Shipment.create_time >= datetime.now() - timedelta(days=30)))
        is_new = float((datetime.now() - address.create_time).days < 7)
        risky = float(address.is_remote_area == 1 or address.address_type == "临时地址")
    return {
        "address_user_count_30d": users,
        "address_is_new": is_new,
        "address_is_remote_or_temporary": risky,
    }


async def compute_all_features(
    db: AsyncSession, user_id: str, order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    result = await compute_user_features(db, user_id)
    if order_id:
        result.update(await compute_order_features(db, order_id))
    else:
        result.update(await compute_order_features(db, ""))
    result.update(await compute_address_features(db, user_id, receive_id))
    return result
