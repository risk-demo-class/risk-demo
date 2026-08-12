"""教育业务事件的实体存在性和归属校验。"""

import logging
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LearningProgress, LiveReward, OrderInfo, RefundRequest, UserInfo
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def ensure_exists(
    db: AsyncSession,
    model: type,
    field_name: str,
    value: Any,
    *,
    entity_label: str,
    field_label: str | None = None,
    cast_value: Callable[[Any], Any] | None = None,
    status_code: int = 404,
) -> None:
    """确认一条业务实体存在；不存在时返回明确的 4xx 错误。"""
    field_label = field_label or f"{entity_label}ID"
    if value is None or value == "":
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    try:
        compare_value = cast_value(value) if cast_value else value
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_label}格式错误: {value}") from exc

    stmt = select(func.count()).select_from(model).where(
        getattr(model, field_name) == compare_value
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在, %s=%s", entity_label, field_label, value)
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


async def ensure_order_belongs_to_user(
    db: AsyncSession, order_id: str, user_id: str
) -> None:
    """保留公共订单归属校验，供报名事件和其他服务复用。"""
    owner = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail=f"报名订单ID不存在: {order_id}")
    if owner != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"报名订单 {order_id} 属于用户 {owner}，与请求用户 {user_id} 不一致",
        )


# event_type -> (实体模型, source_id 对应主键, 展示名称)
_EVENT_SOURCE_VALIDATORS = {
    "课程报名": (OrderInfo, "order_id", "报名订单"),
    "退费申请": (RefundRequest, "refund_id", "退费申请"),
    "直播打赏": (LiveReward, "reward_id", "直播打赏"),
    "学习行为": (LearningProgress, "progress_id", "学习进度"),
}


async def ensure_source_matches_event_type(
    db: AsyncSession, request: RiskCheckRequest
) -> None:
    config = _EVENT_SOURCE_VALIDATORS.get(request.event_type)
    if config is None:
        raise HTTPException(
            status_code=400,
            detail=f"事件类型 {request.event_type} 未配置 source_id 校验规则",
        )
    model, field_name, label = config
    await ensure_exists(
        db,
        model,
        field_name,
        request.source_id,
        entity_label=label,
        field_label=f"{label}ID",
        status_code=400,
    )


async def _get_event_owner(
    db: AsyncSession, request: RiskCheckRequest
) -> str | None:
    """根据事件来源查出真正的业务所有者，防止用他人单据发起检查。"""
    if request.event_type == "课程报名":
        stmt = select(OrderInfo.user_id).where(OrderInfo.order_id == request.source_id)
    elif request.event_type == "退费申请":
        stmt = (
            select(OrderInfo.user_id)
            .select_from(RefundRequest)
            .join(OrderInfo, RefundRequest.order_id == OrderInfo.order_id)
            .where(RefundRequest.refund_id == request.source_id)
        )
    elif request.event_type == "直播打赏":
        stmt = select(LiveReward.user_id).where(LiveReward.reward_id == request.source_id)
    elif request.event_type == "学习行为":
        stmt = select(LearningProgress.user_id).where(
            LearningProgress.progress_id == request.source_id
        )
    else:
        return None
    return (await db.execute(stmt)).scalar_one_or_none()


async def ensure_source_belongs_to_user(
    db: AsyncSession, request: RiskCheckRequest
) -> None:
    owner = await _get_event_owner(db, request)
    if owner is None:
        # 正常情况下存在性校验已拦截；此分支用于防止并发删除或数据断链。
        raise HTTPException(status_code=404, detail=f"事件来源不存在或归属关系缺失: {request.source_id}")
    if owner != request.user_id:
        logger.warning(
            "事件来源归属不一致: event=%s source=%s owner=%s request_user=%s",
            request.event_type,
            request.source_id,
            owner,
            request.user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"{request.event_type}来源 {request.source_id} 属于用户 {owner}，与请求用户 {request.user_id} 不一致",
        )


async def validate_risk_check_request(
    db: AsyncSession, request: RiskCheckRequest
) -> None:
    """按固定顺序完成用户、来源类型和来源归属三项校验。"""
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    await ensure_source_belongs_to_user(db, request)
