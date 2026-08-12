"""
银行风控系统 - 事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (用户/交易/贷款/登录是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (device_id, ip 等)
  3. 黑名单前置拦截 (用户/设备指纹/IP/银行卡号/身份证号, 撞黑就拒)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    BankCard, DeviceFingerprint, IpGeoLocation,
    LoanApplication, LoginLog, Transaction, UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全关联业务参数 (device_id / ip 等, 黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查 (用户 > 设备指纹 > IP > 银行卡号 > 身份证号)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    """黑名单检查 (优先级: 用户 > 设备指纹 > IP > 银行卡号 > 身份证号)"""
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    if request.device_id and await check_blacklist(db, "地址", request.device_id):
        return "设备指纹"
    if request.ip and await check_blacklist(db, "地址", request.ip):
        return "IP"
    if request.card_id:
        card = (await db.execute(
            select(BankCard.card_no_hash).where(BankCard.card_id == request.card_id)
        )).scalar_one_or_none()
        if card and await check_blacklist(db, "手机号", card):
            return "银行卡号"
    user = (await db.execute(
        select(UserInfo.id_card_hash).where(UserInfo.user_id == request.user_id)
    )).first()
    if user and user.id_card_hash and await check_blacklist(db, "手机号", user.id_card_hash):
        return "身份证号"
    return None


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """按 event_type 自动补全关联业务参数."""
    if request.event_type == "转账":
        # source_id = txn_id, 补全 from_card / device_id / ip
        if not request.card_id or not request.device_id or not request.ip:
            row = (await db.execute(
                select(Transaction.from_card, Transaction.device_id, Transaction.ip, Transaction.create_time)
                .where(Transaction.txn_id == request.source_id)
            )).first()
            if row:
                request.card_id = request.card_id or row.from_card
                request.device_id = request.device_id or row.device_id
                request.ip = request.ip or row.ip
                # order_id (引擎兼容) = txn_id
                request.order_id = request.source_id
                # receive_id (引擎兼容) 用 device_id 或 ip
                request.receive_id = request.device_id or request.ip or request.user_id

    elif request.event_type == "贷款申请":
        request.order_id = request.source_id  # 引擎兼容
        request.receive_id = request.user_id  # 引擎兼容

    elif request.event_type == "登录":
        # source_id = login_id, 补全 device_id / ip
        if not request.device_id or not request.ip:
            row = (await db.execute(
                select(LoginLog.device_id, LoginLog.ip, LoginLog.login_at)
                .where(LoginLog.login_id == request.source_id)
            )).first()
            if row:
                request.device_id = request.device_id or row.device_id
                request.ip = request.ip or row.ip
                request.receive_id = request.device_id or request.ip or request.user_id

    return request


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
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