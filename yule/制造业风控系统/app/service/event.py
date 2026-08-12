"""
制造业风控系统 - 事件处理管道 (process_event 统一入口)

4 步业务流 (与电商版流程一致, 不改):
  1. 业务实体校验 (经销商用户/订单/保修单/举报是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id, product_sn)
  3. 黑名单前置拦截 (用户/经销商/设备SN/维修工 4 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

【制造业黑名单优先级】用户 > 经销商 > 设备SN > 维修工; 短路: 一旦撞黑立刻返回
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import CrossRegionReport, OrderInfo, WarrantyRecord
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id / product_sn (黑名单检查需要)
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
    # 1. 用户黑名单 (经销商账号)
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 经销商黑名单: 从订单反查 dealer_id
    dealer_id = await _lookup_dealer_id(db, request)
    if dealer_id and await check_blacklist(db, "经销商", dealer_id):
        return "经销商"

    # 3. 设备SN黑名单: 设备保修事件带 product_sn
    product_sn = (request.event_data or {}).get("product_sn")
    if product_sn and await check_blacklist(db, "设备SN", product_sn):
        return "设备SN"

    # 4. 维修工黑名单: 设备保修事件带 technician_id
    technician_id = (request.event_data or {}).get("technician_id")
    if technician_id and await check_blacklist(db, "维修工", technician_id):
        return "维修工"
    return None


async def _lookup_dealer_id(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    """从订单 / 保修单 / 举报记录反查经销商 ID."""
    order_id = request.order_id or (
        request.source_id if request.event_type == "经销商订货" else None
    )
    if order_id:
        row = (await db.execute(
            select(OrderInfo.dealer_id).where(OrderInfo.order_id == order_id).limit(1)
        )).first()
        if row:
            return row.dealer_id
    if request.event_type == "设备保修":
        row = (await db.execute(
            select(WarrantyRecord.order_id).where(
                WarrantyRecord.warranty_id == request.source_id
            )
        )).first()
        if row and row.order_id:
            row2 = (await db.execute(
                select(OrderInfo.dealer_id).where(OrderInfo.order_id == row.order_id).limit(1)
            )).first()
            if row2:
                return row2.dealer_id
    if request.event_type == "跨区串货举报":
        row = (await db.execute(
            select(CrossRegionReport.dealer_id).where(
                CrossRegionReport.report_id == request.source_id
            )
        )).first()
        if row:
            return row.dealer_id
    return None


# 按 event_type 自动补全 order_id / product_sn
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    event_data = dict(request.event_data or {})

    if request.event_type == "经销商订货":
        # source_id 即 order_id
        if not request.order_id:
            request.order_id = request.source_id

    elif request.event_type == "设备保修":
        # 保修单 → 关联订单 + 设备 SN + 维修工
        if not request.order_id:
            row = (await db.execute(
                select(
                    WarrantyRecord.order_id,
                    WarrantyRecord.product_sn,
                    WarrantyRecord.technician_id,
                ).where(WarrantyRecord.warranty_id == request.source_id)
            )).first()
            if row:
                request.order_id = row.order_id
                event_data.setdefault("product_sn", row.product_sn)
                event_data.setdefault("technician_id", row.technician_id)

    elif request.event_type == "跨区串货举报":
        # 举报记录 → 被举报订单
        if not request.order_id:
            row = (await db.execute(
                select(CrossRegionReport.order_id).where(
                    CrossRegionReport.report_id == request.source_id
                )
            )).first()
            if row:
                request.order_id = row.order_id

    request.event_data = event_data or None
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
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event — 制造业黑名单优先级短路")
    print("=" * 60)

    async def demo_blacklist_priority():
        scenarios = [
            ("只用户撞黑",      ["用户", None, None, None],  "用户"),
            ("只经销商撞黑",    [None, "经销商", None, None], "经销商"),
            ("用户+经销商都撞", ["用户", "经销商", None, None], "用户"),
            ("只设备SN撞黑",    [None, None, "设备SN", None], "设备SN"),
            ("只维修工撞黑",    [None, None, None, "维修工"], "维修工"),
            ("全没撞",          [None, None, None, None],  None),
        ]
        for name, calls, expected in scenarios:
            class _RealDB:
                def __init__(self, calls):
                    self.calls = calls
                    self.idx = 0
                async def execute(self, stmt):
                    s = str(stmt)
                    class _R:
                        def __init__(self, r):
                            self.r = r
                        def scalar(self):
                            return 1 if self.r else 0
                        def scalar_one_or_none(self):
                            return self.r
                        def first(self):
                            return self.r
                    which = self.calls[self.idx]
                    self.idx += 1
                    if which == "经销商":
                        return _R(SimpleNamespace(dealer_id="D001"))
                    if which == "设备SN":
                        return _R(SimpleNamespace(product_sn="SN001"))
                    if which == "维修工":
                        return _R(SimpleNamespace(technician_id="T001"))
                    if which is None:
                        return _R(None)
                    return _R(SimpleNamespace(blacklist_id=1, expire_time=None))

            db = _RealDB(list(calls))
            req = SimpleNamespace(
                user_id="D001",
                order_id="ORD001",
                event_data={"product_sn": "SN001", "technician_id": "T001"},
                event_type="设备保修",
            )
            got = await _check_all_blacklists(db, req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<22} 期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="D001")
    resp = _blacklist_reject(req, blocked_by="经销商")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 order_id / product_sn)")
    print("  3. _check_all_blacklists (短路: 用户 > 经销商 > 设备SN > 维修工)")
    print("  4. run_risk_check (decision.py 7 步流水线)")
