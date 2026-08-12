"""
业务实体校验器.

校验用户存在、事件类型与 source_id 匹配、订单归属一致, 防止横向越权.
"""

import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GroupBooking,
    OrderInfo,
    TicketChangeApplication,
    UserInfo,
    VisaApplication,
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
    """泛型存在性校验."""
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
    try:
        exists = bool((await db.execute(stmt)).scalar())
    except Exception:
        logger.exception("实体存在性校验查询失败: %s=%s", field_label, value)
        raise

    if not exists:
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    """用户必须存在."""
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    """订单必须属于请求用户, 防水平越权."""
    owner = None
    try:
        owner = (
            await db.execute(
                select(OrderInfo.user_id).where(OrderInfo.order_id == order_id).limit(1)
            )
        ).scalar_one_or_none()
    except Exception:
        logger.exception("查询订单归属失败: order_id=%s", order_id)
        raise

    if not owner:
        raise HTTPException(status_code=404, detail=f"订单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id,
            owner,
            user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订单 {order_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


_EVENT_SOURCE_VALIDATORS: dict[tuple[str, ...], tuple[type, str, Optional[Callable], str, int]] = {
    ("下单", "支付"): (OrderInfo, "order_id", None, "订单", 400),
    ("退改申请",): (TicketChangeApplication, "change_id", None, "退改单", 400),
    ("签证申请",): (VisaApplication, "visa_id", None, "签证申请", 400),
    ("拼团报名",): (GroupBooking, "group_id", None, "拼团单", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """source_id 必须匹配 event_type 对应的业务表."""
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db,
            model,
            field,
            request.source_id,
            entity_label=label,
            cast_value=caster,
            status_code=status_code,
        )
        return

    logger.warning("未配置 source_id 校验规则: event_type=%s source_id=%s", request.event_type, request.source_id)


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """风控请求 3 步组合校验."""
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    if request.event_type in ("下单", "支付"):
        order_id = request.order_id or request.source_id
        await ensure_order_belongs_to_user(db, order_id, request.user_id)
    elif request.event_type == "退改申请":
        try:
            order_id = (
                await db.execute(
                    select(TicketChangeApplication.order_id).where(
                        TicketChangeApplication.change_id == request.source_id
                    )
                )
            ).scalar_one_or_none()
        except Exception:
            logger.exception("查询退改单订单失败: change_id=%s", request.source_id)
            raise
        if order_id:
            await ensure_order_belongs_to_user(db, order_id, request.user_id)
    elif request.event_type == "拼团报名":
        try:
            order_id = (
                await db.execute(
                    select(GroupBooking.order_id).where(
                        GroupBooking.group_id == request.source_id
                    )
                )
            ).scalar_one_or_none()
        except Exception:
            logger.exception("查询拼团单订单失败: group_id=%s", request.source_id)
            raise
        if order_id:
            await ensure_order_belongs_to_user(db, order_id, request.user_id)
