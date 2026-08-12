"""
物流业务实体校验器

校验寄件人/运单/投诉/理赔/COD 等实体存在性、事件类型与 source_id 匹配、
运单归属是否与寄件人一致，防止拿他人运单试探风控。
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    LogisticsClaim,
    LogisticsCodSettlement,
    LogisticsComplaint,
    LogisticsSender,
    LogisticsWaybill,
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
    status_code: int = 404,
) -> None:
    """泛型存在性校验: 检查 model.field_name == value 是否存在."""
    field_label = field_label or f"{entity_label}ID"
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    stmt = (
        select(func.count())
        .select_from(model)
        .where(getattr(model, field_name) == value)
        .limit(1)
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(
            status_code=status_code,
            detail=f"{field_label}不存在: {value}",
        )


async def ensure_sender_exists(db: AsyncSession, sender_id: str) -> None:
    """寄件人必须存在 (所有物流风控事件都以寄件人为主主体)."""
    await ensure_exists(db, LogisticsSender, "sender_id", sender_id, entity_label="寄件人")


async def ensure_waybill_belongs_to_sender(
    db: AsyncSession,
    waybill_no: str,
    sender_id: str,
) -> None:
    """防越权: 运单必须属于请求中的寄件人."""
    owner = (await db.execute(
        select(LogisticsWaybill.sender_id).where(LogisticsWaybill.waybill_no == waybill_no).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"运单ID不存在: {waybill_no}")
    if owner != sender_id:
        logger.warning(
            "安全告警: 运单归属不一致 waybill_no=%s, owner=%s, request_sender=%s",
            waybill_no, owner, sender_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"运单 {waybill_no} 属于寄件人 {owner}, 与请求寄件人 {sender_id} 不一致",
        )


# 运单类事件: source_id 就是运单号
WAYBILL_EVENT_TYPES = {
    "寄件下单", "揽收", "中转", "派送", "签收", "拒收", "退回",
    "异常上报", "报关清关", "海外仓", "结汇退税",
}

# 非运单事件: 按事件类型校验 source_id 对应业务单
_SOURCE_VALIDATORS = {
    "投诉": (LogisticsComplaint, "complaint_id", "投诉单"),
    "理赔申请": (LogisticsClaim, "claim_id", "理赔单"),
    "COD结算": (LogisticsCodSettlement, "cod_id", "COD单"),
    "实名认证": (LogisticsSender, "sender_id", "寄件人"),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """按事件类型校验 source_id 是哪种业务单号."""
    if request.event_type in WAYBILL_EVENT_TYPES:
        await ensure_exists(
            db, LogisticsWaybill, "waybill_no", request.source_id,
            entity_label="运单", status_code=400,
        )
        return

    validator = _SOURCE_VALIDATORS.get(request.event_type)
    if validator:
        model, field, label = validator
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label, status_code=400,
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
    """一次跑完物流风控请求的所有校验."""
    # 1. 寄件人存在
    await ensure_sender_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 运单类事件校验归属 (防越权)
    if request.event_type in WAYBILL_EVENT_TYPES:
        await ensure_waybill_belongs_to_sender(db, request.source_id, request.user_id)
