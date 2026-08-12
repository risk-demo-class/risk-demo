"""教育业务实体校验与事件来源派发。"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BusinessEventType
from app.models import LearningProgress, OrderInfo, RefundRequest, UserInfo
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
    """检查业务实体是否存在。"""
    field_label = field_label or f"{entity_label}ID"
    if value is None or value == "":
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")
    try:
        compare_value = cast_value(value) if cast_value else value
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_label}格式错误") from exc

    stmt = select(func.count()).select_from(model).where(getattr(model, field_name) == compare_value)
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


# event_type -> (来源模型, 主键字段, 中文标签, HTTP状态码)
_EVENT_SOURCE_VALIDATORS = {
    (BusinessEventType.COURSE_PURCHASE.value,): (OrderInfo, "order_id", "课程订单", 400),
    (BusinessEventType.REFUND_REQUEST.value,): (RefundRequest, "refund_id", "退费申请", 400),
    (BusinessEventType.LEARNING_ACTIVITY.value,): (LearningProgress, "progress_id", "学习进度", 400),
}


def _source_validator_for(event_type: str):
    for event_types, validator in _EVENT_SOURCE_VALIDATORS.items():
        if event_type in event_types:
            return validator
    return None


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    validator = _source_validator_for(str(request.event_type))
    if validator is None:
        raise HTTPException(status_code=400, detail=f"未配置的教育业务事件类型: {request.event_type}")
    model, field, label, status_code = validator
    await ensure_exists(
        db,
        model,
        field,
        request.source_id,
        entity_label=label,
        status_code=status_code,
    )


async def ensure_source_belongs_to_user(db: AsyncSession, request: RiskCheckRequest) -> None:
    """防止使用本人 user_id 检查其他用户的订单、退费或学习记录。"""
    validator = _source_validator_for(str(request.event_type))
    if validator is None:
        return
    model, field, label, _ = validator
    owner = (
        await db.execute(
            select(model.user_id).where(getattr(model, field) == request.source_id).limit(1)
        )
    ).scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail=f"{label}ID不存在: {request.source_id}")
    if owner != request.user_id:
        logger.warning(
            "安全告警: %s归属不一致 source_id=%s owner=%s request_user=%s",
            label,
            request.source_id,
            owner,
            request.user_id,
        )
        raise HTTPException(status_code=403, detail=f"{label}不属于用户 {request.user_id}")


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    await ensure_source_belongs_to_user(db, request)


if __name__ == "__main__":
    print("教育业务事件校验派发表")
    for event_types, (model, field, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        print(f"  {','.join(event_types):<28} -> {model.__name__}.{field} ({label}, {status})")
