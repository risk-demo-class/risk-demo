"""教育业务实体校验器。

校验三件事：用户存在、source_id 与事件类型匹配、业务记录属于请求用户。
失败时统一抛出 HTTPException，由 FastAPI 转换为 4xx 响应。
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdentityVerification, OrderInfo, RefundRequest, UserInfo
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
    """检查 ``model.field_name == value`` 的记录是否存在。"""
    field_label = field_label or f"{entity_label}ID"
    if value in (None, ""):
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    try:
        compare_value = cast_value(value) if cast_value else value
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_label}格式错误: {value}") from exc

    stmt = select(func.count()).select_from(model).where(
        getattr(model, field_name) == compare_value
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


# event_type -> (业务模型, 主键字段, 用户字段, 中文名称)
_EVENT_SOURCE_VALIDATORS = {
    "课程报名": (OrderInfo, "order_id", "user_id", "报名订单"),
    "退费申请": (RefundRequest, "refund_id", "user_id", "退费申请"),
    "学历认证": (IdentityVerification, "verify_id", "user_id", "认证记录"),
}


def get_event_source_validator(event_type: str) -> tuple[type, str, str, str]:
    """取得事件的业务来源配置；漏配时按服务端配置错误处理。"""
    validator = _EVENT_SOURCE_VALIDATORS.get(event_type)
    if validator is None:
        logger.error("未配置 source_id 校验规则: event_type=%s", event_type)
        raise HTTPException(status_code=500, detail=f"事件类型未配置业务校验: {event_type}")
    return validator


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    model, source_field, _, entity_label = get_event_source_validator(request.event_type)
    await ensure_exists(
        db,
        model,
        source_field,
        request.source_id,
        entity_label=entity_label,
        status_code=400,
    )


async def ensure_source_belongs_to_user(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """防止用户拿他人的真实订单、退费单或认证记录发起检查。"""
    model, source_field, owner_field, entity_label = get_event_source_validator(request.event_type)
    owner = (
        await db.execute(
            select(getattr(model, owner_field))
            .where(getattr(model, source_field) == request.source_id)
            .limit(1)
        )
    ).scalar_one_or_none()

    if owner is None:
        raise HTTPException(status_code=404, detail=f"{entity_label}ID不存在: {request.source_id}")
    if owner != request.user_id:
        logger.warning(
            "安全告警: %s归属不一致 source_id=%s owner=%s request_user=%s",
            entity_label,
            request.source_id,
            owner,
            request.user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"{entity_label} {request.source_id} 属于用户 {owner}，与请求用户 {request.user_id} 不一致",
        )


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """依次执行完整的教育业务请求校验。"""
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    await ensure_source_belongs_to_user(db, request)


if __name__ == "__main__":
    print("教育风控事件与业务来源映射：")
    for event_type, (model, source_field, owner_field, label) in _EVENT_SOURCE_VALIDATORS.items():
        print(f"- {event_type}: {model.__tablename__}.{source_field} -> {owner_field} ({label})")
