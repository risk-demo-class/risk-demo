"""固定四步事件入口：校验、补全、黑名单短路、七步决策。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models_business import Address, Shipment, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    shipment = (await db.execute(select(Shipment).where(
        Shipment.shipment_id == request.order_id))).scalar_one()
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == request.user_id))).scalar_one()
    address = (await db.execute(select(Address).where(
        Address.address_id == shipment.receiver_address_id))).scalar_one()

    checks = (
        ("寄件人", user.user_id), ("证件号", user.id_number_hash),
        ("手机号", user.phone), ("地址", address.address_id),
        ("手机号", address.contact_phone), ("设备指纹", shipment.device_id),
    )
    for blacklist_type, value in checks:
        if value and await check_blacklist(db, blacklist_type, value):
            return _blacklist_reject(request, blacklist_type)
    return await run_risk_check(db, request)


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    stamp = datetime.now()
    return RiskCheckResponse(
        assessment_id="BLACKLIST", event_id="BLACKLIST", user_id=request.user_id,
        final_score=100, risk_level="极高", decision="拒绝", rule_count=0,
        triggered_rules=[], features={}, create_time=stamp, blocked_by=blocked_by,
    )
