"""旅游事件统一入口：校验、上下文补全、黑名单短路、决策流水线。"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import PassengerInfo, PaymentRecord, RiskBlacklist, TravelBlacklistEntry, TravelUser
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.validator import resolve_source_order_and_owner, validate_risk_check_request
from app.service.action_log import record_action

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    request = await _enrich_request(db, request)
    blocked = await _check_all_blacklists(db, request)
    if blocked:
        await record_action(
            db, operator="system", action_type="BLACKLIST_HIT", target_type="blacklist",
            target_id=f"hit:{blocked}:{request.user_id}"[:50],
            after_value={"blocked_by": blocked, "event_type": request.event_type,
                         "source_id": request.source_id, "user_id": request.user_id},
            remark="旅游事件黑名单前置拦截",
        )
        await db.commit()
        return _blacklist_reject(request, blocked)
    return await run_risk_check(db, request)


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    order_id, _ = await resolve_source_order_and_owner(db, request)
    request.order_id = order_id
    # 沿用 receive_id 作为“关联载体 ID”，优先保存当前设备，便于特征快照回溯。
    payment = (await db.execute(select(PaymentRecord).where(PaymentRecord.order_id == order_id)
                                .order_by(PaymentRecord.payment_time.desc()).limit(1))).scalar_one_or_none()
    if payment:
        request.receive_id = payment.device_id
    return request


async def _active_travel_blacklist(db: AsyncSession, entry_type: str, values: list[str]) -> bool:
    if not values:
        return False
    now = datetime.now()
    hit = (await db.execute(select(TravelBlacklistEntry.entry_id).where(
        TravelBlacklistEntry.entry_type == entry_type,
        TravelBlacklistEntry.entry_value_hash.in_(values),
        TravelBlacklistEntry.deleted_at.is_(None),
        (TravelBlacklistEntry.expire_time.is_(None) | (TravelBlacklistEntry.expire_time > now)),
    ).limit(1))).scalar_one_or_none()
    return hit is not None


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    now = datetime.now()
    core_hit = (await db.execute(select(RiskBlacklist.blacklist_id).where(
        RiskBlacklist.blacklist_type == "用户",
        RiskBlacklist.blacklist_value == request.user_id,
        RiskBlacklist.deleted_at.is_(None),
        (RiskBlacklist.expire_time.is_(None) | (RiskBlacklist.expire_time > now)),
    ).limit(1))).scalar_one_or_none()
    if core_hit is not None:
        return "用户"

    user = (await db.execute(select(TravelUser).where(
        TravelUser.user_id == request.user_id))).scalar_one()
    phone_hit = (await db.execute(select(RiskBlacklist.blacklist_id).where(
        RiskBlacklist.blacklist_type == "手机号",
        RiskBlacklist.blacklist_value == user.phone_hash,
        RiskBlacklist.deleted_at.is_(None),
        (RiskBlacklist.expire_time.is_(None) | (RiskBlacklist.expire_time > now)),
    ).limit(1))).scalar_one_or_none()
    if phone_hit is not None:
        return "手机号"

    identities = list((await db.execute(select(PassengerInfo.id_number_hash).where(
        PassengerInfo.user_id == request.user_id))).scalars().all())
    if await _active_travel_blacklist(db, "PASSPORT", identities):
        return "护照号"

    payment = (await db.execute(select(PaymentRecord).where(
        PaymentRecord.order_id == request.order_id).order_by(PaymentRecord.payment_time.desc()).limit(1)
    )).scalar_one_or_none()
    if payment and await _active_travel_blacklist(db, "DEVICE", [payment.device_id]):
        return "设备指纹"
    if payment and await _active_travel_blacklist(db, "IP", [payment.ip]):
        return "IP"
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject", event_id="blacklist_reject",
        user_id=request.user_id, final_score=100, risk_level="极高", decision="拒绝",
        rule_count=0, triggered_rules=[], features={}, create_time=datetime.now(),
        message=f"命中旅游黑名单: {blocked_by}", blocked_by=blocked_by,
    )
