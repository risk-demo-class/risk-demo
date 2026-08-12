"""银行事件处理管道：校验、补全、黑名单短路、七步决策。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import BankCard, BankTransaction, LoanApplication, LoginLog, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    request = await _enrich_request(db, request)
    blocked = await _check_all_blacklists(db, request)
    if blocked:
        return _blacklist_reject(request, blocked)
    return await run_risk_check(db, request)


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    request.order_id = request.source_id
    if request.event_type in ("信用卡交易", "转账"):
        row = (await db.execute(select(BankTransaction.device_id).where(BankTransaction.txn_id == request.source_id))).first()
        if row:
            request.receive_id = row.device_id
    elif request.event_type == "贷款申请":
        row = (await db.execute(select(LoanApplication.device_id).where(LoanApplication.loan_id == request.source_id))).first()
        if row:
            request.receive_id = row.device_id
    elif request.event_type == "登录":
        row = (await db.execute(select(LoginLog.device_id).where(LoginLog.login_id == request.source_id))).first()
        if row:
            request.receive_id = row.device_id
    return request


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    values: list[tuple[str, str | None]] = []
    id_hash = (await db.execute(select(UserInfo.id_card_hash).where(UserInfo.user_id == request.user_id))).scalar_one_or_none()
    values.append(("身份证号", id_hash))
    if request.event_type in ("信用卡交易", "转账"):
        txn = (await db.execute(select(BankTransaction).where(BankTransaction.txn_id == request.source_id))).scalar_one_or_none()
        if txn:
            values.extend([("设备指纹", txn.device_id), ("IP", txn.ip), ("银行卡号", txn.to_card_hash)])
            if txn.from_card_id:
                card_hash = (await db.execute(select(BankCard.card_no_hash).where(BankCard.card_id == txn.from_card_id))).scalar_one_or_none()
                values.append(("银行卡号", card_hash))
    elif request.event_type == "贷款申请":
        loan = (await db.execute(select(LoanApplication).where(LoanApplication.loan_id == request.source_id))).scalar_one_or_none()
        if loan:
            values.extend([("设备指纹", loan.device_id), ("IP", loan.ip)])
    else:
        login = (await db.execute(select(LoginLog).where(LoginLog.login_id == request.source_id))).scalar_one_or_none()
        if login:
            values.extend([("设备指纹", login.device_id), ("IP", login.ip)])
    for blacklist_type, value in values:
        if value and await check_blacklist(db, blacklist_type, value):
            return blacklist_type
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject", event_id="blacklist_reject", user_id=request.user_id,
        final_score=100, risk_level="极高", decision="拒绝", rule_count=0,
        triggered_rules=[], features={}, create_time=datetime.now(), blocked_by=blocked_by,
    )
