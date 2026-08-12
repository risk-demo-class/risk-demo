"""
制造业事件处理管道 (process_event 统一入口)

4 步业务流 (与基线完全一致):
  1. 业务实体校验 (经销商/订货单/保修工单/串货举报是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id)
  3. 黑名单前置拦截 (用户 + 经销商 + 设备SN + 维修工, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单检查规则 (制造业):
  - 用户黑名单: 必查 (任何 event_type, 查核心表 risk_blacklist)
  - 经销商黑名单: 订货/采购/串货事件查被举报或下单经销商 (查业务表 blacklist_extra)
  - 设备SN黑名单: 保修/维修事件查设备序列号
  - 维修工黑名单: 保修/维修事件查维修工
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import CrossRegionReport, OrderInfo, WarrantyRecord
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist, check_blacklist_extra
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id (保修/串货事件需要关联订货单算订单特征)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 经销商 > 设备SN > 维修工; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    if request.event_type in ("经销商订货", "采购订单"):
        dealer_id = (await db.execute(
            select(OrderInfo.dealer_id).where(OrderInfo.order_id == request.source_id).limit(1)
        )).scalar_one_or_none()
        if dealer_id and await check_blacklist_extra(db, "经销商", dealer_id):
            return "经销商"

    elif request.event_type in ("保修申请", "售后维修"):
        row = (await db.execute(
            select(WarrantyRecord.product_sn, WarrantyRecord.technician_id)
            .where(WarrantyRecord.warranty_id == request.source_id)
            .limit(1)
        )).first()
        if row:
            if row.product_sn and await check_blacklist_extra(db, "设备SN", row.product_sn):
                return "设备SN"
            if row.technician_id and await check_blacklist_extra(db, "维修工", row.technician_id):
                return "维修工"

    elif request.event_type == "串货举报":
        dealer_id = (await db.execute(
            select(CrossRegionReport.dealer_id)
            .where(CrossRegionReport.report_id == int(request.source_id))
            .limit(1)
        )).scalar_one_or_none()
        if dealer_id and await check_blacklist_extra(db, "经销商", dealer_id):
            return "经销商"

    return None


# 按 event_type 自动补全 order_id (保修/串货事件从业务表反查)
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in ("经销商订货", "采购订单"):
        if not request.order_id:
            request.order_id = request.source_id

    elif request.event_type in ("保修申请", "售后维修"):
        if not request.order_id:
            row = (await db.execute(
                select(WarrantyRecord.order_id)
                .where(WarrantyRecord.warranty_id == request.source_id)
                .limit(1)
            )).first()
            if row:
                request.order_id = row.order_id

    elif request.event_type == "串货举报":
        if not request.order_id:
            row = (await db.execute(
                select(CrossRegionReport.order_id)
                .where(CrossRegionReport.report_id == int(request.source_id))
                .limit(1)
            )).first()
            if row:
                request.order_id = row.order_id

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
# Demo: _check_all_blacklists 黑名单优先级短路 + _enrich_request — mock DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Service Event — 制造业黑名单优先级短路")
    print("=" * 60)

    print("\n[1] 黑名单检查优先级: 用户 → 经销商 → 设备SN → 维修工 (短路)")
    print("    - 经销商订货/采购订单: 查 用户 + 经销商")
    print("    - 保修申请/售后维修:   查 用户 + 设备SN + 维修工")
    print("    - 串货举报:           查 用户 + 被举报经销商")

    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = RiskCheckRequest(event_type="经销商订货", source_id="ORD001", user_id="D001")
    resp = _blacklist_reject(req, blocked_by="经销商")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 order_id)")
    print("  3. _check_all_blacklists (短路: 用户 > 经销商 > 设备SN > 维修工)")
    print("  4. run_risk_check (decision.py 7 步流水线)")
