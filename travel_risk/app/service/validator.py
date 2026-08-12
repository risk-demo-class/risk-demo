"""
业务实体校验: 风控事件入参必须对得上真实业务数据.

每个业务型 event_type 校验对应业务主键存在且归属正确:
  - 注册:     user_id 存在, source_id == user_id
  - 下单:     booking_id 存在且属于该用户
  - 支付:     payment 存在且属于该用户
  - 退改申请: refund 存在且其订单属于该用户
  - 理赔申请: claim 存在且属于该用户
  - 投诉:     complaint 存在且属于该用户
  - 通用:     只校验用户存在 (用户级/设备级检查)
"""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BookingInfo,
    ClaimInfo,
    ComplaintInfo,
    PaymentInfo,
    RefundChange,
    UserInfo,
)
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    """校验业务实体, 不通过抛 404/400."""
    # 1. 用户必须存在
    user = (await db.execute(
        select(UserInfo.user_id).where(UserInfo.user_id == request.user_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"用户不存在: {request.user_id}")

    event_type = request.event_type
    if event_type == "通用":
        # 用户级/设备级通用检查: 不校验具体业务实体
        return

    if event_type == "注册":
        if request.source_id != request.user_id:
            raise HTTPException(status_code=400, detail="注册事件的 source_id 必须等于 user_id")
        return

    if event_type == "下单":
        booking_id = request.booking_id or request.source_id
        row = (await db.execute(
            select(BookingInfo.user_id).where(BookingInfo.booking_id == booking_id)
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"旅游订单不存在: {booking_id}")
        if row.user_id != request.user_id:
            raise HTTPException(status_code=403, detail="旅游订单不属于该用户")
        return

    if event_type == "支付":
        row = (await db.execute(
            select(PaymentInfo.user_id).where(PaymentInfo.payment_id == request.source_id)
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"支付记录不存在: {request.source_id}")
        if row.user_id != request.user_id:
            raise HTTPException(status_code=403, detail="支付记录不属于该用户")
        return

    if event_type == "退改申请":
        row = (await db.execute(
            select(BookingInfo.user_id)
            .select_from(RefundChange)
            .join(BookingInfo, RefundChange.booking_id == BookingInfo.booking_id)
            .where(RefundChange.refund_id == request.source_id)
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"退改申请不存在: {request.source_id}")
        if row.user_id != request.user_id:
            raise HTTPException(status_code=403, detail="退改申请不属于该用户")
        return

    if event_type == "理赔申请":
        row = (await db.execute(
            select(ClaimInfo.user_id).where(ClaimInfo.claim_id == request.source_id)
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"理赔申请不存在: {request.source_id}")
        if row.user_id != request.user_id:
            raise HTTPException(status_code=403, detail="理赔申请不属于该用户")
        return

    if event_type == "投诉":
        row = (await db.execute(
            select(ComplaintInfo.user_id).where(ComplaintInfo.complaint_id == request.source_id)
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"投诉记录不存在: {request.source_id}")
        if row.user_id != request.user_id:
            raise HTTPException(status_code=403, detail="投诉记录不属于该用户")
        return

    raise HTTPException(status_code=400, detail=f"不支持的事件类型: {event_type}")
