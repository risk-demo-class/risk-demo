"""
事件处理管道 (process_event 统一入口) - 旅游版

4 步业务流:
  1. 业务实体校验 (用户 / 旅游订单 / 签证是否存在)
  2. 自动补全关联业务参数 (order_id)
  3. 黑名单前置拦截 (用户 / 护照号 / 设备指纹 3 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import PassengerInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)

# 带订单的事件类型 (source_id = order_id)
_ORDER_EVENT_TYPES = ("机票预订", "酒店预订", "跟团游预订")


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id (黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate -> event -> feature -> snapshot -> rule -> decision -> persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 护照号 > 设备指纹; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    # 护照号: 按本单乘客证件号撞黑 (旅游黑名单核心类型)
    if request.order_id:
        id_numbers = (await db.execute(
            select(PassengerInfo.id_number).where(PassengerInfo.order_id == request.order_id)
        )).scalars().all()
        for id_number in id_numbers:
            if id_number and await check_blacklist(db, "护照号", id_number):
                return "护照号"
    # 设备指纹: 事件快照里带 device_id 时检查
    if request.event_data and request.event_data.get("device_id"):
        if await check_blacklist(db, "设备指纹", str(request.event_data["device_id"])):
            return "设备指纹"
    return None


# 按事件类型自动补全 order_id (机票/酒店/跟团游 = 订单事件, source_id 即 order_id)
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in _ORDER_EVENT_TYPES and not request.order_id:
        request.order_id = request.source_id
    return request


# 故意不写库: 黑名单拦截不算一次风控评估, 只算"系统保护动作"
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
    print("Service Event (旅游版) — process_event 4 步业务流")
    print("=" * 60)
    print("  1. validate_risk_check_request (validator.py: 用户/订单/签证)")
    print("  2. _enrich_request (机票/酒店/跟团游: source_id -> order_id)")
    print("  3. _check_all_blacklists (短路: 用户 > 护照号 > 设备指纹)")
    print("  4. run_risk_check (decision.py 7 步流水线)")