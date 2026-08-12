"""物流事件合法性和数据归属校验。"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import CustomsDeclaration, DeliveryResult, Shipment, UserInfo
from app.schemas import RiskCheckRequest

_EVENT_SOURCE_VALIDATORS = {
    ("寄件下单", "安检申报", "代收货款结算"): (Shipment, "shipment_id", "运单"),
    ("跨境申报",): (CustomsDeclaration, "declaration_id", "跨境申报"),
    ("签收处理",): (DeliveryResult, "delivery_id", "签收记录"),
}


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    exists = (await db.execute(select(UserInfo.user_id).where(UserInfo.user_id == user_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"寄件人不存在: {user_id}")


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    for event_types, (model, field, label) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type in event_types:
            column = getattr(model, field)
            exists = (await db.execute(select(column).where(column == request.source_id))).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=400, detail=f"{label}不存在或与事件类型不匹配: {request.source_id}")
            return
    raise HTTPException(status_code=400, detail=f"不支持的物流事件: {request.event_type}")


async def _resolve_shipment(db: AsyncSession, request: RiskCheckRequest) -> Shipment:
    if request.event_type in ("寄件下单", "安检申报", "代收货款结算"):
        sid = request.source_id
    elif request.event_type == "跨境申报":
        sid = (await db.execute(select(CustomsDeclaration.shipment_id).where(
            CustomsDeclaration.declaration_id == request.source_id))).scalar_one()
    else:
        sid = (await db.execute(select(DeliveryResult.shipment_id).where(
            DeliveryResult.delivery_id == request.source_id))).scalar_one()
    shipment = (await db.execute(select(Shipment).where(Shipment.shipment_id == sid))).scalar_one()
    request.order_id = shipment.shipment_id
    request.receive_id = shipment.receiver_address_id
    return shipment


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    shipment = await _resolve_shipment(db, request)
    if shipment.sender_user_id != request.user_id:
        raise HTTPException(status_code=403, detail="运单不属于当前寄件人")
    if request.event_type == "跨境申报" and not shipment.is_cross_border:
        raise HTTPException(status_code=400, detail="非跨境件不能发起跨境申报检查")
    if request.event_type == "代收货款结算" and shipment.payment_type != "货到付款":
        raise HTTPException(status_code=400, detail="非货到付款运单不能发起代收货款检查")
