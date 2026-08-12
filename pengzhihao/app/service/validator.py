"""物流风险检查的业务校验。"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Shipment, ShipmentItem, UserInfo
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def ensure_exists(
    db: AsyncSession,
    model: type,
    field_name: str,
    value: Any,
    *,
    entity_label: str,
    field_label: Optional[str] = None,
    cast_value: Optional[Callable[[Any], Any]] = None,
    status_code: int = 404,
) -> None:
    """泛型存在性校验。"""
    field_label = field_label or f"{entity_label}ID"
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")
    compare_value = cast_value(value) if cast_value else value
    stmt = select(func.count()).select_from(model).where(
        getattr(model, field_name) == compare_value
    )
    if not (await db.execute(stmt)).scalar():
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="寄件人")


async def ensure_shipment_belongs_to_user(
    db: AsyncSession, shipment_id: str, user_id: str,
) -> None:
    owner = (await db.execute(
        select(Shipment.sender_id).where(Shipment.shipment_id == shipment_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"运单ID不存在: {shipment_id}")
    if owner != user_id:
        logger.warning(
            "运单归属不一致 shipment_id=%s owner=%s request_user=%s",
            shipment_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"运单 {shipment_id} 属于寄件人 {owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 统一指向 shipment.shipment_id，保留派发表便于新增物流事件。
_EVENT_SOURCE_VALIDATORS = {
    ("寄件受理", "安检验视", "跨境申报", "代收货款"):
        (Shipment, "shipment_id", None, "运单", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession, request: RiskCheckRequest,
) -> None:
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label, cast_value=caster, status_code=status_code,
        )
        return
    raise HTTPException(status_code=400, detail=f"不支持的物流事件: {request.event_type}")


async def _validate_event_precondition(
    db: AsyncSession, request: RiskCheckRequest,
) -> None:
    shipment = (await db.execute(
        select(Shipment).where(Shipment.shipment_id == request.source_id).limit(1)
    )).scalar_one()

    if request.event_type == "安检验视":
        item_count = (await db.execute(
            select(func.count()).select_from(ShipmentItem).where(
                ShipmentItem.shipment_id == request.source_id
            )
        )).scalar() or 0
        if item_count == 0:
            raise HTTPException(status_code=400, detail="安检验视要求运单至少有一条物品明细")
    elif request.event_type == "跨境申报" and not shipment.is_cross_border:
        raise HTTPException(status_code=400, detail="跨境申报事件只能用于跨境运单")
    elif request.event_type == "代收货款" and shipment.payment_type != "代收货款":
        raise HTTPException(status_code=400, detail="代收货款事件只能用于COD运单")


async def validate_risk_check_request(
    db: AsyncSession, request: RiskCheckRequest,
) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    await ensure_shipment_belongs_to_user(db, request.source_id, request.user_id)
    await _validate_event_precondition(db, request)


# 旧测试/外围调用的兼容函数名，语义已变为“运单归属”。
ensure_order_belongs_to_user = ensure_shipment_belongs_to_user
