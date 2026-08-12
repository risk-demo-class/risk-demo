"""银行事件统一入口，保持基线 process_event 四步流程。"""
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import BankCard, BankTransaction, LoanApplication, LoginLog, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 银行业务实体、事件类型、客户归属校验
    await validate_risk_check_request(db, request)
    # 2. 将数据库中的非敏感业务字段补到事件快照
    request = await _enrich_request(db, request)
    # 3. 运营黑名单前置短路
    blocked_by = await _check_all_blacklists(db, request)
    if blocked_by:
        logger.warning("银行黑名单短路: user=%s blocked_by=%s", request.user_id, blocked_by)
        return _blacklist_reject(request, blocked_by)
    # 4. 复用 7 步决策流水线
    return await run_risk_check(db, request)


async def _load_source(db: AsyncSession, request: RiskCheckRequest) -> Any:
    if request.event_type in ("信用卡", "转账"):
        return (await db.execute(
            select(BankTransaction).where(BankTransaction.txn_id == request.source_id)
        )).scalar_one()
    if request.event_type == "贷款":
        return (await db.execute(
            select(LoanApplication).where(LoanApplication.loan_id == request.source_id)
        )).scalar_one()
    return (await db.execute(
        select(LoginLog).where(LoginLog.login_id == request.source_id)
    )).scalar_one()


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """事件快照只放业务解释字段，不放身份证、卡号哈希等敏感值。"""
    source = await _load_source(db, request)
    if request.event_type in ("信用卡", "转账"):
        snapshot = {
            "amount": float(source.amount),
            "channel": source.channel,
            "geo": source.geo,
            "device_id": source.device_id,
            "ip": source.ip,
            "txn_at": source.txn_at.isoformat(),
        }
    elif request.event_type == "贷款":
        snapshot = {
            "amount": float(source.amount),
            "term_months": source.term_months,
            "purpose": source.purpose,
            "institution_code": source.institution_code,
            "debt_ratio": float(source.debt_ratio),
            "apply_at": source.apply_at.isoformat(),
        }
    else:
        snapshot = {
            "device_id": source.device_id,
            "ip": source.ip,
            "geo": source.geo,
            "success": bool(source.success),
            "login_at": source.login_at.isoformat(),
        }
    request.event_data = {**snapshot, **(request.event_data or {})}
    return request


async def _blacklist_candidates(db: AsyncSession, request: RiskCheckRequest) -> list[tuple[str, str]]:
    user = (await db.execute(
        select(UserInfo).where(UserInfo.user_id == request.user_id)
    )).scalar_one()
    source = await _load_source(db, request)
    candidates: list[tuple[str, str]] = [
        ("用户", request.user_id),
        ("身份证号", user.id_card_hash),
    ]
    if request.event_type in ("信用卡", "转账"):
        card_rows = (await db.execute(
            select(BankCard).where(BankCard.card_id.in_([
                value for value in (source.from_card, source.to_card) if value
            ]))
        )).scalars().all()
        card_hashes = [row.card_no_hash for row in card_rows]
        candidates.extend([
            ("设备指纹", source.device_id),
            ("IP", source.ip),
        ])
        candidates.extend(("银行卡号", value) for value in card_hashes)
    else:
        candidates.extend([
            ("设备指纹", source.device_id),
            ("IP", source.ip),
        ])
    return [(kind, value) for kind, value in candidates if value]


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    """运营名单按用户、身份、卡、设备、IP顺序短路。

    blacklist_extra 是外部情报源，通过特征和 R030 等规则留痕，不在此处短路。
    """
    for kind, value in await _blacklist_candidates(db, request):
        if await check_blacklist(db, kind, value):
            return kind
    return None


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
        ml_score=None,
        ml_decision=None,
        blocked_by=blocked_by,
        message=f"命中银行运营黑名单: {blocked_by}",
    )
