"""
业务实体校验器: 教育版 — 校验用户/订单/退费/投诉等业务实体的存在性和归属.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Complaint, Course, OrderInfo, RefundRequest, UserInfo,
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
    """校验用户是否存在"""
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


# event_type → source_id 校验字典 (教育版)
_EVENT_SOURCE_VALIDATORS = {
    ("purchase", "course_watch"):   (OrderInfo,     "order_id",     None,   "订单",     400),
    ("refund_apply",):              (RefundRequest, "refund_id",    None,   "退费申请",  400),
    ("complaint",):                 (Complaint,     "complaint_id", None,   "投诉",     400),
    ("register", "login", "real_name_auth", "coupon_claim"):
                                    (UserInfo,      "user_id",      None,   "用户",     404),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """按 event_type 校验 source_id 存在对应的业务实体"""
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label, cast_value=caster, status_code=status_code,
        )
        return

    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


async def ensure_course_belongs_to_user(
    db: AsyncSession,
    course_id: str | None,
    user_id: str,
) -> None:
    """防水平越权: 检查该用户确实报名了该课程"""
    if not course_id:
        return
    row = (await db.execute(
        select(OrderInfo.user_id).where(
            OrderInfo.course_id == course_id,
            OrderInfo.user_id == user_id,
        ).limit(1)
    )).scalar_one_or_none()
    if not row:
        logger.warning(
            "安全告警: 课程归属不一致 course_id=%s, request_user=%s",
            course_id, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"课程 {course_id} 不属于用户 {user_id}",
        )


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """组合校验: 一次跑完所有跟 request 相关的校验"""
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. purchase 场景: 校验课程归属 (防绕过)
    if request.event_type in ("purchase", "course_watch"):
        await ensure_course_belongs_to_user(db, request.course_id, request.user_id)