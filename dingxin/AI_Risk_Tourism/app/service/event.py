"""
事件处理管道 (process_event 统一入口, 4 步业务流不变)

旅游版适配:
  1. 业务实体校验 (用户/订单/退改/签证是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id)
  3. 黑名单前置拦截 (优先级: 用户 > 签证号 > 设备指纹; 护照走 R030 规则留审计)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单职责 (Q3 决策):
  - 决策只读 risk_blacklist (case.py::check_blacklist 复用)
  - BlacklistExtra 是业务台账, 由写入口镜像, 不参与决策
  - 护照黑名单由规则 R030 拦截 (留审计), 签证/设备由前置快速拦截
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.config import BUSINESS_ORDER_EVENTS, BUSINESS_REFUND_EVENT, BUSINESS_VISA_EVENT
from app.models import OrderInfo, OrderRefund
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id (黑名单护照检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查 (用户 > 护照号 > 签证号 > 设备指纹)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 黑名单检查: 用户 > 签证号 > 设备指纹, 短路
# (Q3 决策: 护照号不走前置拦截, 由规则 R030 拦截并留审计; 前置只做快速保护)
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    # 1. 用户黑名单 (必查)
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 签证号黑名单 (签证申请事件)
    if request.event_type == BUSINESS_VISA_EVENT:
        if await check_blacklist(db, "签证号", request.source_id):
            return "签证号"

    # 3. 设备指纹黑名单 (event_data.device_id 由业务系统传入)
    device_id = (request.event_data or {}).get("device_id")
    if device_id and await check_blacklist(db, "设备指纹", str(device_id)):
        return "设备指纹"

    return None


# 按 event_type 自动补全 order_id (旅游版)
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in BUSINESS_ORDER_EVENTS:
        if not request.order_id:
            request.order_id = request.source_id

    elif request.event_type == BUSINESS_REFUND_EVENT:
        # 退改单 → 订单 (黑名单护照检查需要 order_id 才能取乘客)
        if not request.order_id:
            row = (await db.execute(
                select(OrderRefund.order_id).where(OrderRefund.refund_id == request.source_id)
            )).first()
            if row:
                request.order_id = row.order_id

    elif request.event_type == BUSINESS_VISA_EVENT:
        # 签证场景只算 user 特征, 无订单
        pass

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


# ============================================================
# Demo: 展示 4 步流程 + 黑名单优先级 — 无需 DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Service Event — 旅游版 4 步业务流")
    print("=" * 60)
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 order_id: 预订/支付→source, 退改→退改单, 签证→无)")
    print("  3. _check_all_blacklists (优先级: 用户 > 签证号 > 设备指纹; 护照走 R030)")
    print("  4. run_risk_check (decision.py 7 步流水线)")
    print("\n黑名单职责: risk_blacklist 权威(只读) + BlacklistExtra 业务台账(镜像)")
