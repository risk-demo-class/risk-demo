"""银行版事件入口：公共风控流程 + 银行扩展黑名单前置拦截。"""
import logging
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.engine.decision import run_risk_check
from app.models import BankBlacklistExtra, BankTransaction, LoginLog, LoanApplication
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    blocked = await _check_all_blacklists(db, request)
    if blocked:
        return _blacklist_reject(request, blocked)
    return await run_risk_check(db, request)


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    values = []
    if request.event_type == "大额转账":
        row = (await db.execute(select(BankTransaction).where(BankTransaction.txn_id == request.source_id))).scalar_one_or_none()
        if row:
            values.extend([("银行卡号", row.to_card), ("设备指纹", row.device_id), ("IP", row.ip)])
    elif request.event_type == "异常登录":
        row = (await db.execute(select(LoginLog).where(LoginLog.login_id == request.source_id))).scalar_one_or_none()
        if row:
            values.extend([("设备指纹", row.device_id), ("IP", row.ip)])
    elif request.event_type == "贷款申请":
        row = (await db.execute(select(LoanApplication).where(LoanApplication.loan_id == request.source_id))).scalar_one_or_none()
        if row:
            values.append(("身份证号", request.user_id))
    for blacklist_type, value in values:
        stmt = select(func.count()).select_from(BankBlacklistExtra).where(BankBlacklistExtra.blacklist_type == blacklist_type, BankBlacklistExtra.blacklist_value == value)
        if (await db.execute(stmt)).scalar():
            return blacklist_type
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject", event_id="blacklist_reject", user_id=request.user_id,
        final_score=100, risk_level="极高", decision="拒绝", rule_count=0,
        triggered_rules=[], features={}, create_time=datetime.now(), ml_score=None,
        ml_decision=None, blocked_by=blocked_by, message=f"命中银行黑名单: {blocked_by}",
    )

