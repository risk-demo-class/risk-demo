"""
业务实体校验器 (物流行业版): 集中处理运单/申报/投诉等业务实体的存在性、一致性校验.
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Shipment,
    CustomsDeclaration,
    ComplaintRecord,
    UserInfo,
    Address,
)
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
    """泛型存在性校验"""
    field_label = field_label or f"{entity_label}ID"
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    compare_value = cast_value(value) if cast_value else value
    stmt = (
        select(func.count())
        .select_from(model)
        .where(getattr(model, field_name) == compare_value)
        .limit(1)
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(
            status_code=status_code,
            detail=f"{field_label}不存在: {value}",
        )


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


async def ensure_shipment_belongs_to_sender(
    db: AsyncSession,
    shipment_id: str,
    user_id: str,
) -> None:
    """防越权: 校验运单寄件人是否为当前用户"""
    owner = (await db.execute(
        select(Shipment.sender_user_id).where(Shipment.shipment_id == shipment_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"运单ID不存在: {shipment_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 运单归属不一致 shipment_id=%s, sender=%s, request_user=%s",
            shipment_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"运单 {shipment_id} 寄件人为 {owner}, 与请求用户 {user_id} 不一致",
        )


async def ensure_declaration_belongs_to_shipment(
    db: AsyncSession,
    declaration_id: str,
    shipment_id: str,
) -> None:
    """校验申报记录属于指定运单"""
    row = (await db.execute(
        select(CustomsDeclaration.shipment_id).where(
            CustomsDeclaration.declaration_id == declaration_id
        ).limit(1)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"申报ID不存在: {declaration_id}")
    if row != shipment_id:
        raise HTTPException(
            status_code=403,
            detail=f"申报 {declaration_id} 属于运单 {row}, 与运单 {shipment_id} 不一致",
        )


# ===== 物流行业: source_id 与 event_type 匹配的校验派发表 =====
_EVENT_SOURCE_VALIDATORS = {
    ("寄件下单",): (Shipment, "shipment_id", None, "运单", 400),
    ("到付签收",): (Shipment, "shipment_id", None, "运单", 400),
    ("跨境申报",): (CustomsDeclaration, "declaration_id", None, "跨境申报", 400),
    ("投诉申诉",): (ComplaintRecord, "record_id", int, "投诉记录", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """字典派发: 按 event_type 找到对应的业务表做存在性校验"""
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label,
            cast_value=caster,
            status_code=status_code,
        )
        return

    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """物流版: 组合校验链"""
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 寄件下单/到付签收: 校验运单归属 (防越权)
    if request.event_type in ("寄件下单", "到付签收"):
        shipment_id = request.order_id or request.source_id
        await ensure_shipment_belongs_to_sender(db, shipment_id, request.user_id)

    # 4. 跨境申报: 校验申报与运单的一致性 (如果传了 order_id=shipment_id)
    if request.event_type == "跨境申报" and request.order_id:
        await ensure_declaration_belongs_to_shipment(
            db, declaration_id=request.source_id, shipment_id=request.order_id,
        )


if __name__ == "__main__":
    print("=" * 60)
    print("Service Validator (物流版) — 字典派发表")
    print("=" * 60)
    print("\n[1] 事件派发 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<10} {'model':<22} {'field':<18} {'label':<10}")
    for evt_types, (model, field, _, label, _) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<10} {model.__name__:<22} {field:<18} {label:<10}")

    print("\n[2] 校验链 validate_risk_check_request:")
    print("  ① ensure_user_exists → 用户存在")
    print("  ② ensure_source_matches_event_type → source_id 匹配 event_type")
    print("  ③ ensure_shipment_belongs_to_sender → 寄件下单/到付签收: 运单归属防越权")
    print("  ④ ensure_declaration_belongs_to_shipment → 跨境申报: 申报归属运单")
