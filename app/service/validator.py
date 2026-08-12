"""教育业务实体校验：报名、退费、直播打赏三类事件。"""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Enrollment, LiveReward, RefundRequest, UserInfo
from app.schemas import RiskCheckRequest


async def ensure_exists(db: AsyncSession, model: type, field_name: str, value: Any, *, entity_label: str, **_) -> None:
    if not value:
        raise HTTPException(status_code=400, detail=f"{entity_label}ID不能为空")
    count = (await db.execute(select(func.count()).select_from(model).where(getattr(model, field_name) == value))).scalar()
    if not count:
        raise HTTPException(status_code=404, detail=f"{entity_label}ID不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


_EVENT_SOURCE_VALIDATORS = {
    ("课程报名",): (Enrollment, "enrollment_id", "报名记录"),
    ("退费申请",): (RefundRequest, "refund_id", "退费申请"),
    ("直播打赏",): (LiveReward, "reward_id", "打赏记录"),
}


def _get_source_validator(event_type: str):
    """从“事件类型元组 → 校验器”的配置中找到当前事件对应项。"""
    for event_types, validator in _EVENT_SOURCE_VALIDATORS.items():
        if event_type in event_types:
            return validator
    raise HTTPException(status_code=400, detail=f"不支持的教育事件类型: {event_type}")


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    model, field, label = _get_source_validator(request.event_type)
    await ensure_exists(db, model, field, request.source_id, entity_label=label)


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    if request.event_type == "课程报名":
        owner = (await db.execute(select(Enrollment.user_id).where(Enrollment.enrollment_id == request.source_id))).scalar_one()
        if owner != request.user_id:
            raise HTTPException(status_code=403, detail="报名记录不属于该用户")
    if request.event_type == "退费申请":
        owner = (await db.execute(select(RefundRequest.user_id).where(RefundRequest.refund_id == request.source_id))).scalar_one()
        if owner != request.user_id:
            raise HTTPException(status_code=403, detail="退费申请不属于该用户")
    if request.event_type == "直播打赏":
        owner = (await db.execute(select(LiveReward.user_id).where(LiveReward.reward_id == request.source_id))).scalar_one()
        if owner != request.user_id:
            raise HTTPException(status_code=403, detail="打赏记录不属于该用户")
