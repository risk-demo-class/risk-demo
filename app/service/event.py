"""
事件处理管道 (物流行业版): process_event 统一入口
4 步业务流:
  1. 业务实体校验 (用户/运单/申报/投诉是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id=shipment_id, receive_id=receiver_address_id)
  3. 黑名单前置拦截 (用户/身份证/手机号/地址/运单号)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import Shipment, CustomsDeclaration, ComplaintRecord, Address
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id / receive_id (黑名单检查需要 receive_id)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


# ===== 黑名单检查: 用户 > 身份证号 > 手机号 > 地址 > 运单号 (短路) =====
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    # 1. 用户黑名单 (必查)
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 地址黑名单 (有 receive_id=receiver_address_id 时查)
    if request.receive_id and await check_blacklist(db, "地址", request.receive_id):
        return "地址"

    # 3. 手机号黑名单 (从 address.contact_phone 查)
    if request.receive_id:
        row = (await db.execute(
            select(Address.contact_phone).where(Address.address_id == request.receive_id)
        )).first()
        if row and row.contact_phone and await check_blacklist(db, "手机号", row.contact_phone):
            return "手机号"

    # 4. 运单号黑名单 (有 order_id=shipment_id 时查 waybill_no)
    shipment_id = request.order_id or request.source_id
    if shipment_id and request.event_type in ("寄件下单", "到付签收"):
        row = (await db.execute(
            select(Shipment.waybill_no).where(Shipment.shipment_id == shipment_id)
        )).first()
        if row and row.waybill_no and await check_blacklist(db, "运单号", row.waybill_no):
            return "运单号"

    return None


# ===== 按 event_type 补全 order_id=shipment_id 和 receive_id=receiver_address_id =====
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in ("寄件下单", "到付签收"):
        # source_id = shipment_id
        if not request.order_id:
            request.order_id = request.source_id
        if not request.receive_id and request.order_id:
            row = (await db.execute(
                select(Shipment.receiver_address_id).where(
                    Shipment.shipment_id == request.order_id
                )
            )).first()
            if row:
                request.receive_id = row.receiver_address_id

    elif request.event_type == "跨境申报":
        # source_id = declaration_id → 找 shipment_id → 找 receiver_address_id
        if not request.order_id:
            row = (await db.execute(
                select(CustomsDeclaration.shipment_id).where(
                    CustomsDeclaration.declaration_id == request.source_id
                )
            )).first()
            if row:
                request.order_id = row.shipment_id
        if not request.receive_id and request.order_id:
            row = (await db.execute(
                select(Shipment.receiver_address_id).where(
                    Shipment.shipment_id == request.order_id
                )
            )).first()
            if row:
                request.receive_id = row.receiver_address_id

    elif request.event_type == "投诉申诉":
        # source_id = complaint_record.record_id → 找 shipment_id → 找 address
        if not request.order_id:
            row = (await db.execute(
                select(ComplaintRecord.shipment_id).where(
                    ComplaintRecord.record_id == int(request.source_id)
                )
            )).first()
            if row:
                request.order_id = row.shipment_id
        if not request.receive_id and request.order_id:
            row = (await db.execute(
                select(Shipment.receiver_address_id).where(
                    Shipment.shipment_id == request.order_id
                )
            )).first()
            if row:
                request.receive_id = row.receiver_address_id

    return request


# ===== 黑名单拦截: 不写库, 直接返回 =====
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


if __name__ == "__main__":
    print("=" * 60)
    print("Service Event (物流版) — 4 种事件派发 + 5 级黑名单短路")
    print("=" * 60)
    print("\n[1] event_type → 补全逻辑 _enrich_request:")
    print("  寄件下单 / 到付签收:")
    print("    order_id ← source_id (shipment_id)")
    print("    receive_id ← Shipment.receiver_address_id")
    print("  跨境申报:")
    print("    order_id ← CustomsDeclaration.shipment_id")
    print("    receive_id ← Shipment.receiver_address_id (通过 order_id 二次查)")
    print("  投诉申诉:")
    print("    order_id ← ComplaintRecord.shipment_id (record_id → int)")
    print("    receive_id ← Shipment.receiver_address_id")
    print("\n[2] 黑名单优先级 (短路) _check_all_blacklists:")
    print("  ① 用户 (user_id) → 必查")
    print("  ② 地址 (receive_id=receiver_address_id) → 有 receive_id 时查")
    print("  ③ 手机号 (Address.contact_phone) → 查 address 表拿 phone")
    print("  ④ 运单号 (Shipment.waybill_no) → 寄件/到付签收场景查")
    print("  ⑤ 设备指纹 → 保留扩展, 需 request.event_data.device_fingerprint")
