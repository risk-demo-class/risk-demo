"""
校验器 — 6 个 ensure_* 横向越权防护 + 请求校验
教育场景: 报名/缴费/退费/考试/作业 5 类事件
攻击场景: 攻击者拿自己的 user_id + 别人的 enrollment_id 调风控。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Enrollment, ExamRecord, HomeworkRecord, PaymentRecord, RefundRecord, UserInfo,
)

# 字典驱动: event_type → (对应业务表, source 字段名, 错误信息, HTTP 状态码)
_EVENT_SOURCE_VALIDATORS = {
    "报名": (Enrollment, "enrollment_id", "报名单", 400),
    "缴费": (PaymentRecord, "payment_id", "缴费单", 400),
    "退费": (RefundRecord, "refund_id", "退费单", 400),
    "考试": (ExamRecord, "exam_id", "考试记录", 400),
    "作业": (HomeworkRecord, "homework_id", "作业记录", 400),
}

# 事件类型 → 需要校验"业务单据属于该用户"的字段(按各事件自身的单据号)
# 5 类事件均强制归属校验: 防拿自己的 user_id + 别人的单据号调风控(横向越权)
_EVENT_USER_OWNERSHIP = {
    "报名": "enrollment_id",
    "缴费": "payment_id",
    "退费": "refund_id",
    "考试": "exam_id",
    "作业": "homework_id",
}


async def ensure_user_exists(db: AsyncSession, user_id: str):
    """步骤 1: 用户必须存在。"""
    r = await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"学员不存在: {user_id}")


async def ensure_source_matches_event_type(db: AsyncSession, event_type: str, source_id: str):
    """步骤 2: source_id 必须在对应业务表存在。"""
    entry = _EVENT_SOURCE_VALIDATORS.get(event_type)
    if not entry:
        raise HTTPException(status_code=400, detail=f"不支持的事件类型: {event_type}")
    model, field, label, code = entry
    r = await db.execute(select(model).where(getattr(model, field) == source_id))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=code, detail=f"{label}不存在: {source_id}")


async def ensure_business_belongs_to_user(db: AsyncSession, event_type: str,
                                          user_id: str, source_id: str):
    """步骤 3: 业务单据必须属于该用户(防横向越权)。"""
    field = _EVENT_USER_OWNERSHIP.get(event_type)
    if not field:
        return  # 字典外的事件类型不强制归属(当前 5 类均在内)

    model, _, _, _ = _EVENT_SOURCE_VALIDATORS[event_type]
    r = await db.execute(
        select(model).where(getattr(model, field) == source_id, model.user_id == user_id))
    if not r.scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail=f"业务单据 {source_id} 不属于学员 {user_id}(越权访问被拒绝)")


async def ensure_event_type_supported(event_type: str):
    """步骤 0: 事件类型白名单。"""
    if event_type not in _EVENT_SOURCE_VALIDATORS:
        raise HTTPException(status_code=400, detail=f"不支持的事件类型: {event_type}")


async def validate_risk_check_request(db: AsyncSession, payload: dict):
    """
    入口校验: 用户存在 → 事件类型支持 → source 匹配 → 归属校验。
    对应安检"身份核验"。
    """
    event_type = payload.get("event_type")
    user_id = payload.get("user_id")
    source_id = payload.get("source_id")

    if not event_type or not user_id or not source_id:
        raise HTTPException(status_code=400, detail="event_type/user_id/source_id 必填")

    await ensure_event_type_supported(event_type)
    await ensure_user_exists(db, user_id)
    await ensure_source_matches_event_type(db, event_type, source_id)
    await ensure_business_belongs_to_user(db, event_type, user_id, source_id)
