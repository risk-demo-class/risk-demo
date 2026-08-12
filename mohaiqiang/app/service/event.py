"""
物流事件处理管道 (process_event 统一入口)

流程:
  1. 业务实体校验 (寄件人/运单/投诉/理赔/COD 等)
  2. 自动补全运单/收件人/地址/快递员
  3. 黑名单前置拦截 (寄件人/地址/手机号)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    LogisticsClaim,
    LogisticsCodSettlement,
    LogisticsComplaint,
    LogisticsRecipient,
    LogisticsSender,
    LogisticsWaybill,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import WAYBILL_EVENT_TYPES, validate_risk_check_request

logger = logging.getLogger(__name__)


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """按事件类型补全 waybill_no / recipient_id / address_id / operator_id."""
    waybill_no: str | None = None

    if request.event_type in WAYBILL_EVENT_TYPES:
        waybill_no = request.source_id
    elif request.event_type == "投诉":
        row = (await db.execute(
            select(LogisticsComplaint.waybill_no).where(
                LogisticsComplaint.complaint_id == request.source_id
            )
        )).scalar_one_or_none()
        waybill_no = row
    elif request.event_type == "理赔申请":
        waybill_no = (await db.execute(
            select(LogisticsClaim.waybill_no).where(LogisticsClaim.claim_id == request.source_id)
        )).scalar_one_or_none()
    elif request.event_type == "COD结算":
        waybill_no = (await db.execute(
            select(LogisticsCodSettlement.waybill_no).where(
                LogisticsCodSettlement.cod_id == request.source_id
            )
        )).scalar_one_or_none()

    if waybill_no:
        waybill = (await db.execute(
            select(LogisticsWaybill).where(LogisticsWaybill.waybill_no == waybill_no)
        )).scalar_one_or_none()
        if waybill:
            request.recipient_id = request.recipient_id or waybill.recipient_id
            request.address_id = request.address_id or waybill.address_id
            request.operator_id = request.operator_id or waybill.operator_id
            request.event_data = request.event_data or {}
            request.event_data["waybill_no"] = waybill_no
    return request


async def _check_all_blacklists(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> str | None:
    """优先级: 寄件人 > 地址 > 寄件人手机号 > 收件人手机号."""
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    if request.address_id and await check_blacklist(db, "地址", request.address_id):
        return "地址"

    sender = (await db.execute(
        select(LogisticsSender.sender_phone).where(LogisticsSender.sender_id == request.user_id)
    )).scalar_one_or_none()
    if sender and await check_blacklist(db, "手机号", sender):
        return "手机号"

    if request.recipient_id:
        recipient = (await db.execute(
            select(LogisticsRecipient.recipient_phone).where(
                LogisticsRecipient.recipient_id == request.recipient_id
            )
        )).scalar_one_or_none()
        if recipient and await check_blacklist(db, "手机号", recipient):
            return "手机号"
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """黑名单拦截: 不写审计, 直接返回拒绝."""
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


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全运单/收件人/地址/快递员
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning(
            "撞黑名单: type=%s, sender=%s, source=%s",
            blocked, request.user_id, request.source_id,
        )
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)
