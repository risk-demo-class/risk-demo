"""
事件处理管道 (process_event 统一入口)

4 步业务流程:
  1. 业务实体校验 (用户/运单是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (shipment_id, dest_address_id)
  3. 黑名单前置拦截 (用户/地址/手机号 3 种类型; 撞黑就拒, 不再走 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单规则:
  - 用户黑名单: 必查 (任何 event_type)
  - 地址黑名单: 有 receive_id (目的地址) 时查
  - 手机号黑名单: 运单场景查 shipment.receiver_phone
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import Shipment
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 shipment_id / dest_address_id
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎
    return await run_risk_check(db, request)


async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    """黑名单优先级: 用户 -> 地址 -> 手机号 (短路)."""
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    if request.receive_id and await check_blacklist(db, "地址", request.receive_id):
        return "地址"
    if request.event_type.startswith("shipment_") and request.source_id:
        row = (await db.execute(
            select(Shipment.receiver_phone).where(Shipment.shipment_id == request.source_id)
        )).first()
        if row and row.receiver_phone and await check_blacklist(db, "手机号", row.receiver_phone):
            return "手机号"
    return None


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """补全关联业务参数:
    - shipment_create / shipment_cancel / shipment_receive: source_id 就是运单号,
      从 shipment 表补 dest_address_id (目的地址ID)
    - id_verification: 无运单/地址关联
    """
    if request.event_type in ("shipment_create", "shipment_cancel", "shipment_receive"):
        if not request.order_id:
            request.order_id = request.source_id
        if not request.receive_id and request.order_id:
            row = (await db.execute(
                select(Shipment.dest_address_id).where(Shipment.shipment_id == request.order_id)
            )).first()
            if row:
                request.receive_id = row.dest_address_id
    return request


# 故意不写库: 黑名单拦截不算一次风控评估, 只算"系统保护动作",
# 不写 risk_event/risk_assessment, 避免审计噪音
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
# Demo: _check_all_blacklists 黑名单优先级短路 + _enrich_request 补全
# 运行方式: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from unittest.mock import patch
    import app.service.event as event_module

    print("=" * 60)
    print("Service Event - 黑名单优先级短路 (用户 > 地址 > 手机号)")
    print("=" * 60)

    async def demo_blacklist_priority():
        scenarios = [
            ("只用户撞黑",     "用户"),
            ("只地址撞黑",     "地址"),
            ("用户+地址都撞",  "用户"),
            ("只手机号撞黑",   "手机号"),
            ("全没撞",         None),
        ]
        for name, hit_type in scenarios:
            async def fake_check(_db, btype, _value):
                return btype == hit_type

            class _RealDB:
                async def execute(self, stmt):
                    class _R:
                        receiver_phone = "13800001111"
                    return _R()

            db = _RealDB()
            req = SimpleNamespace(user_id="U001", receive_id="rec_001",
                                  event_type="shipment_create", source_id="SHIP_1")
            with patch.object(event_module, "check_blacklist", side_effect=fake_check):
                got = await _check_all_blacklists(db, req)
            mark = "OK" if got == hit_type else "FAIL"
            print(f"  [{mark}] {name:<20} 期望={hit_type} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # _blacklist_reject 行为
    print("\n[2] _blacklist_reject (不写库, 直接返回响应):")
    req = SimpleNamespace(user_id="U001")
    resp = _blacklist_reject(req, blocked_by="用户")
    print(f"  assessment_id = '{resp.assessment_id}'")
    print(f"  decision      = '{resp.decision}'  blocked_by = '{resp.blocked_by}'")

    print("\n" + "=" * 60)
    print("总结: 用户 > 地址 > 手机号 三级黑名单, 撞黑即拒, 不走 7 步流程")
