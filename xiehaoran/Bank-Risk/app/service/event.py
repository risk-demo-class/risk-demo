"""
事件处理管道 (process_event 统一入口, 银行语义)

4 步业务流:
  1. 业务实体校验 (event_type 合法性)
  2. 自动补全关联业务参数 (order_id)
  3. 黑名单前置拦截 (银行 6 维度: account/device/ip/phone/id_card/merchant/beneficiary)
  4. 调用风控决策引擎 run_risk_check (7 步)

银行域没有电商业务表, 黑名单检查基于事件传入的字段 + risk_blacklist 表.
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BANK_EVENT_TYPES, BLACKLIST_TYPE_KEYS
from app.engine.decision import run_risk_check
from app.models_risk import RiskBlacklist
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist

logger = logging.getLogger(__name__)


def _validate_request(request: RiskCheckRequest) -> None:
    if request.event_type not in BANK_EVENT_TYPES:
        raise ValueError(f"未知业务事件类型: {request.event_type}, 合法值={list(BANK_EVENT_TYPES)}")


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    """银行 6 维度黑名单检查, 短路返回第一个命中维度."""
    ed = request.event_data or {}
    # 待查的 (维度, 值) 列表
    candidates = [
        ("account", request.user_id),
        ("device", ed.get("device_fingerprint")),
        ("ip", ed.get("ip_addr")),
        ("phone", ed.get("phone")),
        ("id_card", ed.get("id_card")),
        ("merchant", ed.get("merchant_id")),
        ("beneficiary", ed.get("beneficiary_id")),
    ]
    for btype, value in candidates:
        if value and await check_blacklist(db, btype, str(value)):
            return btype
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="freeze",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        message=f"撞黑名单: {blocked_by}",
        blocked_by=blocked_by,
    )


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    _validate_request(request)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)
    return await run_risk_check(db, request)
