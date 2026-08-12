"""制造业事件入口的实体存在性、来源归属和关联完整性校验。"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.industry_mapping import get_event_mapping
from app.models import CrossRegionReport, Dealer, Device, PurchaseOrder, WarrantyClaim
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
    """检查指定业务实体是否存在。"""
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
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    """兼容函数名；user_id 在制造业入口中统一表示 dealer_id。"""
    await ensure_exists(
        db,
        Dealer,
        "dealer_id",
        user_id,
        entity_label="经销商",
        field_label="经销商ID",
    )


def _reject_owner_mismatch(entity_label: str, source_id: str, owner: str, dealer_id: str) -> None:
    logger.warning(
        "安全告警: %s归属不一致 source_id=%s, owner=%s, request_dealer=%s",
        entity_label,
        source_id,
        owner,
        dealer_id,
    )
    raise HTTPException(
        status_code=403,
        detail=f"{entity_label} {source_id} 属于经销商 {owner}, 与请求经销商 {dealer_id} 不一致",
    )


async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    """兼容函数名；校验采购订单属于当前经销商。"""
    owner = (await db.execute(
        select(PurchaseOrder.dealer_id)
        .where(PurchaseOrder.po_id == order_id)
        .limit(1)
    )).scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail=f"采购订单ID不存在: {order_id}")
    if owner != user_id:
        _reject_owner_mismatch("采购订单", order_id, owner, user_id)


async def _validate_warranty_claim(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    row = (await db.execute(
        select(WarrantyClaim.dealer_id, WarrantyClaim.device_id)
        .where(WarrantyClaim.claim_id == request.source_id)
        .limit(1)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"保修申请ID不存在: {request.source_id}")
    if row.dealer_id != request.user_id:
        _reject_owner_mismatch("保修申请", request.source_id, row.dealer_id, request.user_id)
    await ensure_exists(
        db,
        Device,
        "device_id",
        row.device_id,
        entity_label="设备",
        field_label="设备ID",
    )


async def _validate_cross_region_report(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    report = (await db.execute(
        select(CrossRegionReport.device_id)
        .where(CrossRegionReport.report_id == request.source_id)
        .limit(1)
    )).first()
    if report is None:
        raise HTTPException(status_code=404, detail=f"串货举报ID不存在: {request.source_id}")

    device = (await db.execute(
        select(Device.device_id, Device.dealer_id)
        .where(Device.device_id == report.device_id)
        .limit(1)
    )).first()
    if device is None:
        raise HTTPException(status_code=404, detail=f"设备ID不存在: {report.device_id}")

    supplied_dealer_id = (request.event_data or {}).get("dealer_id")
    owner = device.dealer_id or supplied_dealer_id
    if owner is None:
        raise HTTPException(
            status_code=400,
            detail="设备未关联经销商时，event_data.dealer_id 不能为空",
        )
    if owner != request.user_id:
        _reject_owner_mismatch("串货举报关联设备", request.source_id, owner, request.user_id)


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """按集中映射校验 source_id 的表、归属经销商及必需关联。"""
    mapping = get_event_mapping(request.event_type)

    if mapping.source_entity == "purchase_order":
        await ensure_order_belongs_to_user(db, request.source_id, request.user_id)
        return
    if mapping.source_entity == "warranty_claim":
        await _validate_warranty_claim(db, request)
        return
    if mapping.source_entity == "cross_region_report":
        await _validate_cross_region_report(db, request)
        return

    raise HTTPException(status_code=400, detail=f"未配置的制造业事件来源: {mapping.source_entity}")


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """完整入口校验：经销商存在，然后校验事件来源及归属。"""
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
