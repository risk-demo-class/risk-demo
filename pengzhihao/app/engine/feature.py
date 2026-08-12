"""物流业务特征工程。

核心 XGBoost 的 25 个键保持不变；其物流语义见 README。三个前缀仍分别写入
风险特征表的用户/订单/地址实体，页面会把“订单”展示为“运单”。
"""
from datetime import datetime, timedelta

from sqlalchemy import case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Address, Shipment, ShipmentItem, UserInfo


async def _count(model, db: AsyncSession, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史寄件总数。"""
    return await _count(Shipment, db, sender_id=user_id)


async def _feat_user_orders_30d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id, Shipment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_orders_7d(db: AsyncSession, user_id: str) -> float:
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id, Shipment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史代收货款总敞口。"""
    stmt = select(func.coalesce(func.sum(Shipment.cod_amount), 0)).where(
        Shipment.sender_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    return round(await _feat_user_total_amount(db, user_id) / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    stmt = select(func.coalesce(func.max(Shipment.cod_amount), 0)).where(
        Shipment.sender_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """COD 拒收次数。"""
    return await _count(Shipment, db, sender_id=user_id, cod_status="拒收")


async def _feat_user_postsale_count(db: AsyncSession, user_id: str) -> float:
    """危险品/验视异常次数。"""
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id,
        Shipment.inspection_status.in_(["疑似危险品", "拒绝收寄"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    return round(await _feat_user_refund_count(db, user_id) / total_orders, 4)


async def _feat_user_postsale_rate(
    db: AsyncSession, user_id: str, total_orders: float | None = None,
) -> float:
    if total_orders is None:
        total_orders = await _feat_user_total_orders(db, user_id)
    if total_orders == 0:
        return 0
    return round(await _feat_user_postsale_count(db, user_id) / total_orders, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    stmt = select(func.coalesce(func.sum(Shipment.cod_amount), 0)).where(
        Shipment.sender_id == user_id, Shipment.cod_status == "拒收",
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id,
        Shipment.shipment_status.in_(["拒收退回", "已取消"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """实名异常标志（兼容旧 complaint_count 数值槽位）。"""
    status = (await db.execute(
        select(UserInfo.real_name_status).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    return 0.0 if status == "已核验" else 1.0


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    stmt = select(func.count(distinct(Shipment.receiver_address_id))).where(
        Shipment.sender_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    total_orders = await _feat_user_total_orders(db, user_id)
    independent = {
        "user_orders_30d": _feat_user_orders_30d,
        "user_orders_7d": _feat_user_orders_7d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_order_amount": _feat_user_max_order_amount,
        "user_refund_count": _feat_user_refund_count,
        "user_postsale_count": _feat_user_postsale_count,
        "user_refund_amount": _feat_user_refund_amount,
        "user_cancel_count": _feat_user_cancel_count,
        "user_complaint_count": _feat_user_complaint_count,
        "user_address_count": _feat_user_address_count,
    }
    features = {name: await fn(db, user_id) for name, fn in independent.items()}
    features["user_total_orders"] = total_orders
    features["user_avg_order_amount"] = await _feat_user_avg_order_amount(
        db, user_id, total_orders=total_orders
    )
    features["user_refund_rate"] = await _feat_user_refund_rate(
        db, user_id, total_orders=total_orders
    )
    features["user_postsale_rate"] = await _feat_user_postsale_rate(
        db, user_id, total_orders=total_orders
    )
    return features


async def _shipment_row(db: AsyncSession, shipment_id: str):
    return (await db.execute(
        select(Shipment).where(Shipment.shipment_id == shipment_id)
    )).scalar_one_or_none()


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """8 个运单特征；order_id 参数实际为 shipment_id。"""
    shipment = await _shipment_row(db, order_id)
    if not shipment:
        return {name: 0.0 for name in (
            "order_total_amount", "order_item_count", "order_sku_count",
            "order_discount_amount", "order_discount_rate", "order_pay_interval_sec",
            "order_is_night", "order_category_count",
        )}
    item_stmt = select(
        func.count(ShipmentItem.item_id),
        func.coalesce(func.sum(ShipmentItem.quantity), 0),
        func.coalesce(func.sum(case(
            (
                or_(
                    ShipmentItem.inspection_result.in_(["禁寄", "信息不符"]),
                    (ShipmentItem.detected_dangerous_type.is_not(None))
                    & (ShipmentItem.dangerous_declared == 0),
                ),
                1,
            ),
            else_=0,
        )), 0),
    ).where(ShipmentItem.shipment_id == order_id)
    item_count, quantity, dangerous_count = (await db.execute(item_stmt)).one()
    declared_weight = float(shipment.declared_weight_kg or 0)
    actual_weight = float(shipment.actual_weight_kg or 0)
    weight_diff = abs(actual_weight - declared_weight)
    weight_rate = weight_diff / declared_weight if declared_weight > 0 else (1.0 if actual_weight else 0.0)
    pickup_interval = 0.0
    if shipment.pickup_time:
        pickup_interval = max(0.0, (shipment.pickup_time - shipment.create_time).total_seconds())
    return {
        "order_total_amount": float(shipment.declared_value or 0),
        "order_item_count": float(item_count or 0),
        "order_sku_count": float(quantity or 0),
        "order_discount_amount": round(weight_diff, 4),
        "order_discount_rate": round(weight_rate, 4),
        "order_pay_interval_sec": round(pickup_interval, 2),
        "order_is_night": 1.0 if 0 <= shipment.create_time.hour < 6 else 0.0,
        "order_category_count": float(dangerous_count or 0),
    }


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None,
) -> dict[str, float]:
    province_stmt = select(func.count(distinct(Address.province))).select_from(Shipment).join(
        Address, Shipment.receiver_address_id == Address.address_id
    ).where(Shipment.sender_id == user_id)
    province_count = float((await db.execute(province_stmt)).scalar() or 0)
    if not receive_id:
        return {
            "addr_total_count": 0.0,
            "addr_province_count": province_count,
            "addr_is_new": 0.0,
        }
    address = (await db.execute(
        select(Address).where(Address.address_id == receive_id)
    )).scalar_one_or_none()
    if not address:
        return {"addr_total_count": 0.0, "addr_province_count": province_count, "addr_is_new": 0.0}
    shared_stmt = select(func.count(distinct(Shipment.sender_id))).select_from(Shipment).join(
        Address, Shipment.receiver_address_id == Address.address_id
    ).where(Address.normalized_hash == address.normalized_hash)
    shared_senders = float((await db.execute(shared_stmt)).scalar() or 0)
    usage_stmt = select(func.count()).select_from(Shipment).where(
        Shipment.sender_id == user_id, Shipment.receiver_address_id == receive_id,
    )
    usage_count = int((await db.execute(usage_stmt)).scalar() or 0)
    high_risk = address.is_remote == 1 or address.address_type == "临时" or usage_count <= 1
    return {
        "addr_total_count": shared_senders,
        "addr_province_count": province_count,
        "addr_is_new": 1.0 if high_risk else 0.0,
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
