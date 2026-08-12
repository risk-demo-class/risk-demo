"""
事件处理管道 (process_event 统一入口, 物流版)

4 步业务流:
  1. 业务实体校验 (寄件人 / 运单是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (shipment_id, address_id)
  3. 黑名单前置拦截 (用户/身份证号/地址/手机号, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单检查顺序: 用户 > 身份证号 > 地址 > 手机号 (短路).
身份证号黑名单存业务表 blacklist_extra (物流行业扩展黑名单).
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import BlacklistExtra, Shipment, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 shipment_id / address_id (黑名单检查需要 address_id)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s",
                       blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 身份证号 > 地址 > 手机号; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 身份证号黑名单 (blacklist_extra 表)
    row = (await db.execute(
        select(UserInfo.id_number_hash).where(UserInfo.user_id == request.user_id)
    )).first()
    if row and row.id_number_hash and await _check_blacklist_extra(db, "身份证号", row.id_number_hash):
        return "身份证号"

    if request.address_id and await check_blacklist(db, "地址", request.address_id):
        return "地址"

    # 手机号: 优先运单收件人手机, 没有运单就用寄件人手机
    phone = None
    if request.shipment_id:
        row = (await db.execute(
            select(Shipment.receiver_phone).where(Shipment.shipment_id == request.shipment_id)
        )).first()
        if row:
            phone = row.receiver_phone
    if not phone:
        row = (await db.execute(
            select(UserInfo.phone).where(UserInfo.user_id == request.user_id)
        )).first()
        phone = row.phone if row else None
    if phone and await check_blacklist(db, "手机号", phone):
        return "手机号"
    return None


async def _check_blacklist_extra(db: AsyncSession, blacklist_type: str, value: str) -> bool:
    """查物流行业扩展黑名单 (blacklist_extra), 未过期才算命中."""
    row = (await db.execute(
        select(BlacklistExtra).where(
            BlacklistExtra.blacklist_type == blacklist_type,
            BlacklistExtra.blacklist_value == value,
        )
    )).first()
    if not row:
        return False
    bl = row[0]
    if bl.expire_time and bl.expire_time < datetime.now():
        return False
    return True


# 按 event_type 自动补全 shipment_id / address_id
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in ("寄件", "跨境申报", "代收货款"):
        if not request.shipment_id:
            request.shipment_id = request.source_id
        if not request.address_id and request.shipment_id:
            row = (await db.execute(
                select(Shipment.address_id).where(Shipment.shipment_id == request.shipment_id)
            )).first()
            if row:
                request.address_id = row.address_id
    elif request.event_type == "实名认证":
        # source_id 就是 user_id, 不关联运单
        pass
    return request


# 撞黑拦截不写库: 不算一次风控评估, 避免审计噪音
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


# ============================================================
# Demo: 黑名单优先级短路 + _enrich_request (mock DB)
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Service Event (物流版) — 黑名单优先级短路")
    print("=" * 60)
    print("  检查顺序: 用户 → 身份证号 → 地址 → 手机号 (短路)")
    print("  身份证号黑名单来源: blacklist_extra 表 (物流行业扩展)")
    print("  _enrich_request: 寄件/跨境申报/代收货款 补全 shipment_id/address_id")
