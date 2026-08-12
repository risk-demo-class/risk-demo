"""物流事件适配管道。

公开请求使用物流术语；进入未修改的七步核心引擎前转换为基线 ENUM。
process_event 仍严格保持：校验 → 补全 → 黑名单 → run_risk_check 四步。
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CORE_RULE_CATEGORY_TO_LOGISTICS, LOGISTICS_EVENT_TO_CORE
from app.engine.decision import run_risk_check
from app.models import Address, BlacklistExtra, Shipment, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


@dataclass
class _InternalRiskRequest:
    """只在业务适配层与核心引擎之间传递，不属于公开 API。"""

    event_type: str
    source_id: str
    user_id: str
    event_data: Optional[dict[str, Any]] = None
    order_id: str = ""
    receive_id: str = ""


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全运单/地址并映射核心 ENUM
    internal_request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, internal_request)
    if blocked is not None:
        logger.warning("撞物流黑名单: type=%s user_id=%s", blocked, request.user_id)
        return _blacklist_reject(internal_request, blocked)

    # 4. 未修改的决策引擎 7 步
    response = await run_risk_check(db, internal_request)
    for hit in response.triggered_rules:
        hit.rule_category = CORE_RULE_CATEGORY_TO_LOGISTICS.get(
            hit.rule_category, hit.rule_category
        )
    return response


async def _enrich_request(
    db: AsyncSession, request: RiskCheckRequest,
) -> _InternalRiskRequest:
    row = (await db.execute(
        select(Shipment.receiver_address_id).where(
            Shipment.shipment_id == request.source_id
        )
    )).first()
    if not row:
        # 正常会在第 1 步被拦截，这里只做防御性兜底。
        raise ValueError(f"运单不存在: {request.source_id}")
    event_data = dict(request.event_data or {})
    event_data["business_event_type"] = request.event_type
    event_data["shipment_id"] = request.source_id
    return _InternalRiskRequest(
        event_type=LOGISTICS_EVENT_TO_CORE[request.event_type],
        source_id=request.source_id,
        user_id=request.user_id,
        event_data=event_data,
        order_id=request.source_id,
        receive_id=row.receiver_address_id,
    )


async def _extra_blacklist_hit(
    db: AsyncSession, entity_type: str, entity_value: str | None,
) -> bool:
    if not entity_value:
        return False
    now = datetime.now()
    stmt = select(BlacklistExtra.extra_id).where(
        BlacklistExtra.entity_type == entity_type,
        BlacklistExtra.entity_value == entity_value,
        BlacklistExtra.status == "启用",
        or_(BlacklistExtra.expire_time.is_(None), BlacklistExtra.expire_time > now),
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _check_all_blacklists(
    db: AsyncSession, request: _InternalRiskRequest,
) -> str | None:
    """核心三类 + 物流扩展四类黑名单，命中后短路。"""
    if await check_blacklist(db, "用户", request.user_id):
        return "寄件人"
    if await check_blacklist(db, "地址", request.receive_id):
        return "收件地址"

    address = (await db.execute(
        select(Address.contact_phone).where(Address.address_id == request.receive_id)
    )).scalar_one_or_none()
    user = (await db.execute(
        select(UserInfo).where(UserInfo.user_id == request.user_id)
    )).scalar_one()
    for phone in (user.phone, address):
        if phone and await check_blacklist(db, "手机号", phone):
            return "联系电话"

    extra_values = (
        ("实名证件", user.id_no_hash),
        ("设备指纹", user.device_fingerprint),
        ("IP地址", user.last_ip),
    )
    for entity_type, value in extra_values:
        if await _extra_blacklist_hit(db, entity_type, value):
            return entity_type

    customs_subject = (await db.execute(
        select(Shipment.customs_subject).where(Shipment.shipment_id == request.source_id)
    )).scalar_one_or_none()
    if await _extra_blacklist_hit(db, "海关主体", customs_subject):
        return "海关主体"
    return None


def _blacklist_reject(request: _InternalRiskRequest, blocked_by: str) -> RiskCheckResponse:
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
