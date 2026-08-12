"""
事件处理流水线 process_event.

4 步业务流:
1. 业务实体校验
2. 自动补全关联业务参数
3. 黑名单前置拦截
4. 调用决策引擎 run_risk_check
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    GroupBooking,
    OrderInfo,
    PassengerInfo,
    TicketChangeApplication,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """风控事件统一入口."""
    try:
        # 1. 业务实体校验
        await validate_risk_check_request(db, request)

        # 2. 自动补全
        request = await _enrich_request(db, request)

        # 3. 黑名单前置拦截
        blocked = await _check_all_blacklists(db, request)
        if blocked is not None:
            logger.warning(
                "撞黑名单: type=%s user_id=%s source_id=%s",
                blocked,
                request.user_id,
                request.source_id,
            )
            return _blacklist_reject(request, blocked)

        # 4. 决策引擎
        return await run_risk_check(db, request)
    except Exception:
        logger.exception("process_event 失败: event_type=%s source_id=%s", request.event_type, request.source_id)
        raise


async def _enrich_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckRequest:
    """按事件类型补全 order_id / receive_id(乘客关联ID)."""
    try:
        if request.event_type in ("下单", "支付"):
            request.order_id = request.order_id or request.source_id
            if request.order_id and not request.receive_id:
                passenger_id = (
                    await db.execute(
                        select(PassengerInfo.passenger_id)
                        .where(PassengerInfo.order_id == request.order_id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if passenger_id:
                    request.receive_id = passenger_id

        elif request.event_type == "退改申请":
            row = (
                await db.execute(
                    select(TicketChangeApplication.order_id)
                    .where(TicketChangeApplication.change_id == request.source_id)
                    .limit(1)
                )
            ).first()
            if row:
                request.order_id = row.order_id
                passenger_id = (
                    await db.execute(
                        select(PassengerInfo.passenger_id)
                        .where(PassengerInfo.order_id == request.order_id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if passenger_id:
                    request.receive_id = passenger_id

        elif request.event_type == "拼团报名":
            row = (
                await db.execute(
                    select(GroupBooking.order_id)
                    .where(GroupBooking.group_id == request.source_id)
                    .limit(1)
                )
            ).first()
            if row:
                request.order_id = row.order_id

        return request
    except Exception:
        logger.exception("事件补全失败: event_type=%s source_id=%s", request.event_type, request.source_id)
        raise


async def _check_all_blacklists(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> str | None:
    """黑名单优先级: 用户 -> 手机号 -> 护照号 -> 设备 -> 支付账号 -> IP."""
    try:
        if await check_blacklist(db, "用户", request.user_id):
            return "用户"

        order = None
        if request.order_id:
            order = (
                await db.execute(
                    select(OrderInfo).where(OrderInfo.order_id == request.order_id).limit(1)
                )
            ).scalar_one_or_none()

        if order:
            if order.pay_account and await check_blacklist(db, "支付账号", order.pay_account):
                return "支付账号"
            if order.device_id and await check_blacklist(db, "设备指纹", order.device_id):
                return "设备指纹"
            if order.ip_address and await check_blacklist(db, "IP", order.ip_address):
                return "IP"

        passengers = []
        if request.order_id:
            passengers = list(
                (
                    await db.execute(
                        select(PassengerInfo).where(PassengerInfo.order_id == request.order_id)
                    )
                ).scalars().all()
            )
        elif request.receive_id:
            passenger = (
                await db.execute(
                    select(PassengerInfo)
                    .where(PassengerInfo.passenger_id == request.receive_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if passenger:
                passengers = [passenger]

        for p in passengers:
            if p.phone and await check_blacklist(db, "手机号", p.phone):
                return "手机号"
            if p.passport_no and await check_blacklist(db, "护照号", p.passport_no):
                return "护照号"
            if p.id_number and await check_blacklist(db, "护照号", p.id_number):
                return "护照号"

        return None
    except Exception:
        logger.exception("黑名单检查失败: user_id=%s", request.user_id)
        raise


def _blacklist_reject(
    request: RiskCheckRequest,
    blocked_by: str,
) -> RiskCheckResponse:
    """黑名单拦截不写风控评估表, 直接返回拒绝."""
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="拒绝",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        blocked_by=blocked_by,
    )
