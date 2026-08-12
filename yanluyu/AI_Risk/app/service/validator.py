"""
教育业务实体校验器: 集中处理"用户/订单/退费/课程/打赏"等实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Course,
    DonationRecord,
    OrderInfo,
    RefundRequest,
    UserInfo,
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
    """泛型存在性校验: 检查 model.field_name == value 的记录是否存在."""
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


async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    """防越权: 订单属于该用户"""
    owner = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"订单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订单 {order_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 与 event_type 的校验规则 (字典派发)
_EVENT_SOURCE_VALIDATORS = {
    ("报名",): (OrderInfo, "order_id", None, "订单", 400),
    ("退费申请",): (RefundRequest, "refund_id", None, "退费申请", 400),
    ("打赏",): (DonationRecord, "donation_id", None, "打赏记录", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
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


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 报名场景: 校验订单归属 (防绕过)
    if request.event_type == "报名":
        order_id = request.order_id or request.source_id
        await ensure_order_belongs_to_user(db, order_id, request.user_id)
