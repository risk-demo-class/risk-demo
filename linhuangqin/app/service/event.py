"""
事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (用户/订单/售后是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id, receive_id)
  3. 黑名单前置拦截 (用户/地址/手机号 3 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

【P1-S9 修复 2026-08-07】原代码只查"用户"黑名单, "地址"和"手机号"加了也用不上.
现在按以下规则查:
  - 用户黑名单: 必查 (任何 event_type)
  - 地址黑名单: 有 receive_id 时查 (下单/支付/售后 都有)
  - 手机号黑名单: 有 receive_id 时, 查 receive_info.receiver_phone
所以 enrich_request 提到撞黑检查之前, 保证 receive_id 已知.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import ConsigneeInfo, WaybillInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id (waybill_id) / consignee_id (黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查: 卖家 > 买家 > 手机号 (短路)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, seller_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 卖家 > 买家 > 手机号; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "卖家", request.user_id):
        return "卖家"
    if request.receive_id and await check_blacklist(db, "买家", request.receive_id):
        return "买家"
    if request.receive_id:
        row = (await db.execute(
            select(ConsigneeInfo.consignee_phone).where(ConsigneeInfo.consignee_id == request.receive_id)
        )).first()
        if row and row.consignee_phone and await check_blacklist(db, "手机号", row.consignee_phone):
            return "手机号"
    return None


# 按 event_type 自动补全 order_id (waybill_id) / receive_id (consignee_id)
# if/elif 不用字典派发: SQL 差异大, if/elif 更易读
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    # 运单类事件: source_id 就是 waybill_id, 补 consignee_id
    if request.event_type in ("卖家下单寄件", "揽收入仓", "出仓发货", "运输中",
                              "派送中", "买家签收", "买家拒收", "买家退回寄件"):
        if not request.order_id:
            request.order_id = request.source_id
        if not request.receive_id and request.order_id:
            row = (await db.execute(
                select(WaybillInfo.consignee_id).where(WaybillInfo.waybill_id == request.order_id)
            )).first()
            if row:
                request.receive_id = row.consignee_id

    elif request.event_type in ("验货完成", "退货入仓验货"):
        # source_id 是验货记录 record_id, 通过运单关联
        # (验货场景: waybill_id 由调用方在 order_id 传入, 这里只补 consignee)
        if request.order_id and not request.receive_id:
            row = (await db.execute(
                select(WaybillInfo.consignee_id).where(WaybillInfo.waybill_id == request.order_id)
            )).first()
            if row:
                request.receive_id = row.consignee_id

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
        # 【P4-L5 2026-08-10】ml_score 保持 None, 前端不渲染 ML 评分块
        # message 直接告诉用户"为什么拒绝", 不需要他懂 blocked_by 字段语义
        message=f"撞黑名单: {blocked_by}",
        blocked_by=blocked_by,
    )


# ============================================================
# Demo: _check_all_blacklists 黑名单优先级短路 + _enrich_request — mock DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event — 黑名单优先级短路 (P1-S9)")
    print("=" * 60)

    # 1. _check_all_blacklists 子函数: 卖家 > 买家 > 手机号
    print("\n[1] 黑名单检查优先级: 卖家 → 买家 → 手机号 (短路)")

    async def demo_blacklist_priority():
        # 模拟 5 种场景
        # _check_all_blacklists 内部调用顺序: 卖家黑名单 → 买家黑名单 → consignee_phone → 手机号黑名单
        scenarios = [
            ("只卖家撞黑",     ["卖家", None,  None,  None],  "卖家"),
            ("只买家撞黑",     [None,  "买家", None,  None],  "买家"),
            ("卖家+买家都撞",  ["卖家", "买家", None,  None],  "卖家"),
            ("只手机号撞黑",   [None,  None,  "phone","手机号"], "手机号"),
            ("全没撞",         [None,  None,  None,  None],  None),
        ]
        for name, calls, expected in scenarios:
            class _RealDB:
                def __init__(self, calls):
                    self.calls = calls
                    self.idx = 0
                async def execute(self, stmt):
                    class _R:
                        def __init__(self, r): self.r = r
                        def scalar(self): return 1 if self.r else 0
                        def scalar_one_or_none(self): return self.r
                        def first(self): return self.r
                    which = self.calls[self.idx]
                    self.idx += 1
                    # calls[2] 是 consignee_phone 查询, 总是返手机号
                    if which == "phone":
                        return _R(SimpleNamespace(consignee_phone="13800001111"))
                    if which is None:
                        return _R(None)
                    # 黑名单命中: 返 ORM 对象
                    return _R(SimpleNamespace(blacklist_id=1, expire_time=None))

            db = _RealDB(list(calls))
            req = SimpleNamespace(user_id="SHP0001", receive_id="CG0001")
            got = await _check_all_blacklists(db, req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<22} 调用序列={calls}  期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # 2. _blacklist_reject 子函数: 返回 RiskCheckResponse
    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="SHP0001")
    resp = _blacklist_reject(req, blocked_by="卖家")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  risk_level    = '{resp.risk_level}'")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (P1-S9 新字段, 区分撞的哪种)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    # 3. process_event 主入口: 4 步业务流
    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 waybill_id / consignee_id)")
    print("  3. _check_all_blacklists (短路: 卖家 > 买家 > 手机号)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 黑名单拦截是独立 1 步, 审计 noise 0 (不写 risk_event/case)")
