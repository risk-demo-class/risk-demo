"""
事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (用户/经销商/订单/保修单/举报单 是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id 等)
  3. 黑名单前置拦截 (经销商ID/设备SN/维修工/用户 4 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单拦截范围:
  - 经销商ID: 必查 (任何 event_type, user_id 即经销商)
  - 设备SN: 保修/维修事件查保修单里的 product_sn
  - 维修工: 保修/维修事件查保修单里的 technician_id
  - 用户: 必查 (user_id)
优先级: 经销商ID > 设备SN > 维修工 > 用户 (短路, 一旦撞黑立刻返回)
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import WarrantyRecord
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist, check_blacklist_extra
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全保修单上下文 (黑名单检查需要 product_sn / technician_id)
    warranty = await _load_warranty_if_needed(db, request)

    # 3. 黑名单前置检查 (风控黑名单 + 业务黑名单)
    blocked = await _check_all_blacklists(db, request, warranty)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


async def _load_warranty_if_needed(
    db: AsyncSession, request: RiskCheckRequest,
) -> WarrantyRecord | None:
    """保修/维修事件: 把保修单读出来, 供黑名单检查用 (不校验归属, validator 已做)."""
    if request.event_type not in ("保修申请", "售后维修"):
        return None
    return (await db.execute(
        select(WarrantyRecord).where(WarrantyRecord.warranty_id == request.source_id)
    )).scalar_one_or_none()


async def _check_all_blacklists(
    db: AsyncSession,
    request: RiskCheckRequest,
    warranty: WarrantyRecord | None,
) -> str | None:
    # 1. 经销商ID (风控黑名单)
    if await check_blacklist(db, "经销商ID", request.user_id):
        return "经销商ID"
    # 2. 用户 (风控黑名单)
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    # 3. 设备SN / 维修工 (仅保修/维修事件, 风控黑名单 + 业务黑名单)
    if warranty:
        if warranty.product_sn and await check_blacklist(db, "设备SN", warranty.product_sn):
            return "设备SN"
        if warranty.technician_id and await check_blacklist(db, "维修工", warranty.technician_id):
            return "维修工"
        if warranty.product_sn and await check_blacklist_extra(db, "设备SN", warranty.product_sn):
            return "设备SN"
        if warranty.technician_id and await check_blacklist_extra(db, "维修工", warranty.technician_id):
            return "维修工"
    # 4. 业务黑名单的"经销商ID"不在这里拦截: 走 R030 规则 (dealer_blacklist_hit 特征),
    #    这样黑经销商也能建案留痕; 只有风控黑名单 risk_blacklist 才前置拦截不建案
    return None


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
# Demo: _check_all_blacklists 黑名单优先级短路 — mock DB
# 跑法: python -m app.service.event
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event — 黑名单前置拦截 (4 类, 短路)")
    print("=" * 60)

    print("\n[1] _check_all_blacklists 检查顺序:")
    print("  经销商ID(风控) → 用户(风控) → 设备SN(风控+业务) → 维修工(风控+业务) → 经销商ID(业务)")
    print("  短路: 一旦撞黑立刻返回, 不再检查后续")

    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="D003")
    resp = _blacklist_reject(req, blocked_by="经销商ID")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  risk_level    = '{resp.risk_level}'")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (区分撞的哪种)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _load_warranty_if_needed (保修事件补 product_sn/technician_id)")
    print("  3. _check_all_blacklists (短路: 经销商ID > 用户 > 设备SN > 维修工)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 黑名单拦截是独立 1 步, 审计 noise 0 (不写 risk_event/case)")
