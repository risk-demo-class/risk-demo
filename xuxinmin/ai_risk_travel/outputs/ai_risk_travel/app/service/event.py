"""
旅游风控系统 - 事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (用户/订单/签证申请是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id)
  3. 黑名单前置拦截 (用户/手机号/证件/设备指纹/IP, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单类型按行业定义: 用户 / 护照号 / 身份证号 / 手机号 / 设备指纹 / IP / 签证号
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import OrderInfo, PassengerInfo, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id (黑名单检查需要订单/乘客信息)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


# 优先级: 用户 > 手机号 > 设备指纹 > IP > 乘客证件; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 手机号黑名单 (从用户档案取)
    user = (await db.execute(
        select(UserInfo.phone).where(UserInfo.user_id == request.user_id)
    )).first()
    if user and user.phone and await check_blacklist(db, "手机号", user.phone):
        return "手机号"

    # 设备指纹黑名单 (事件快照里带 device_id 才查)
    if request.event_data and request.event_data.get("device_id"):
        device_id = str(request.event_data["device_id"])
        if await check_blacklist(db, "设备指纹", device_id):
            return "设备指纹"

    # IP 黑名单 (事件快照里带 ip 才查)
    if request.event_data and request.event_data.get("ip"):
        ip = str(request.event_data["ip"])
        if await check_blacklist(db, "IP", ip):
            return "IP"

    # 乘客证件黑名单 (护照号 / 身份证号): 只有订单类事件才有乘客
    if request.order_id:
        passengers = (await db.execute(
            select(PassengerInfo.id_number).where(PassengerInfo.order_id == request.order_id)
        )).scalars().all()
        for id_number in passengers:
            if not id_number:
                continue
            if await check_blacklist(db, "护照号", id_number):
                return "护照号"
            if await check_blacklist(db, "身份证号", id_number):
                return "身份证号"

    return None


# 按 event_type 自动补全 order_id
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in ("预订", "支付", "退改签"):
        # source_id 就是 order_id
        if not request.order_id:
            request.order_id = request.source_id
    elif request.event_type == "签证申请":
        # source_id 是 visa_id, 不关联订单, 只算用户维度特征
        pass
    return request


# 故意不写库: 黑名单拦截不算一次风控评估
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
# Demo: 黑名单优先级短路 + 补全逻辑 — mock DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Service Event — 旅游黑名单优先级短路")
    print("=" * 60)

    print("\n[1] 黑名单检查优先级: 用户 → 手机号 → 设备指纹 → IP → 乘客证件 (短路)")
    print("  _check_all_blacklists 内部调用顺序见源码注释")

    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = RiskCheckRequest(event_type="预订", source_id="ORD001", user_id="U001")
    resp = _blacklist_reject(req, blocked_by="护照号")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 order_id)")
    print("  3. _check_all_blacklists (短路)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 黑名单拦截是独立 1 步, 审计 noise 0 (不写 risk_event/case)")
