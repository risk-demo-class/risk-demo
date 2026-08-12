"""
事件处理管道 (process_event 统一入口) — 旅游行业版

4 步业务流 (流程不变, 业务分支换成旅游实体):
  1. 业务实体校验 (用户/订单/签证申请是否存在, 订单归属是否一致)
  2. 自动补全关联业务参数 (order_id = source_id)
  3. 黑名单前置拦截 (用户/护照号/设备指纹/IP 4 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

旅游行业黑名单检查规则:
  - 用户黑名单: 必查 (任何 event_type)
  - 护照号黑名单: 订单类事件查订单乘客证件号; 签证申请查 event_data.passport/id_number
  - 设备指纹 / IP 黑名单: 查 event_data.device_id / event_data.ip
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import OrderInfo, PassengerInfo
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
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 护照号 > 设备指纹 > IP; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    event_data = request.event_data or {}

    # 1) 订单类事件: 查订单乘客证件号 (黑护照拦截)
    if request.event_type in ("预订下单", "支付成功", "出票确认", "退改签申请", "出行核销", "索赔投诉", "评价发布"):
        order_id = request.order_id or request.source_id
        if order_id:
            rows = (await db.execute(
                select(PassengerInfo.id_number).where(PassengerInfo.order_id == order_id)
            )).all()
            for row in rows:
                if row.id_number and await check_blacklist(db, "护照号", row.id_number):
                    return "护照号"

    # 2) 无订单事件 (签证申请): 查事件快照里的证件号
    passport = event_data.get("passport") or event_data.get("id_number")
    if passport and await check_blacklist(db, "护照号", passport):
        return "护照号"

    # 3) 设备指纹 / IP
    device_id = event_data.get("device_id")
    if device_id and await check_blacklist(db, "设备指纹", device_id):
        return "设备指纹"
    ip = event_data.get("ip")
    if ip and await check_blacklist(db, "IP", ip):
        return "IP"
    return None


# 按 event_type 自动补全 order_id (旅游行业没有 receive_id 概念)
# 签证申请以 visa_id 为 source_id, 无订单关联, 跳过
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in ("预订下单", "支付成功", "出票确认", "退改签申请", "出行核销", "索赔投诉", "评价发布"):
        if not request.order_id:
            request.order_id = request.source_id
    elif request.event_type == "签证申请":
        # 签证申请只算 user + event_data 特征, 不关联订单, 跳过
        pass

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
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch

    print("=" * 60)
    print("Service Event — 黑名单优先级短路 (旅游行业版)")
    print("=" * 60)

    # 1. _check_all_blacklists 子函数: 用户 > 护照号 > 设备指纹 > IP
    print("\n[1] 黑名单检查优先级: 用户 → 护照号 → 设备指纹 → IP (短路)")

    async def demo_blacklist_priority():
        # hits=黑名单命中的类型集合; evt_override=None→订单类事件, "签证申请"→无订单事件
        scenarios = [
            ("只用户撞黑",     {"用户"},           "用户",   None),
            ("只护照号撞黑",   {"护照号"},         "护照号", None),
            ("用户+护照都撞",  {"用户", "护照号"}, "用户",   None),
            ("只设备指纹撞黑", {"设备指纹"},       "设备指纹", None),
            ("只IP撞黑",       {"IP"},            "IP",     None),
            ("签证事件撞护照", {"护照号"},         "护照号", "签证申请"),
            ("全没撞",         set(),             None,     None),
        ]
        for name, hits, expected, evt_override in scenarios:
            class _RealDB:
                async def execute(self, stmt):
                    class _R:
                        def __init__(self, rows): self.rows = rows
                        def all(self): return self.rows
                    # 订单类事件查乘客证件号: 护照号场景返回 1 个证件号, 其他返回空
                    if "护照号" in hits and evt_override is None:
                        return _R([SimpleNamespace(id_number="E12345678")])
                    return _R([])

            evt_type = evt_override or "预订下单"
            event_data = {"device_id": "dev_abc", "ip": "1.2.3.4"}
            if evt_type == "签证申请":
                event_data["passport"] = "G87654321"
            req = SimpleNamespace(
                user_id="U001", order_id="ORD001", source_id="ORD001",
                event_type=evt_type, event_data=event_data,
            )

            async def fake_check(_db, btype, _value):
                return btype in hits

            # 注意: -m / runpy 执行时本模块以 __main__ 身份重跑,
            # patch 必须打在 __main__ 命名空间 (sys.modules[__name__]),
            # 不能打真实模块 app.service.event (两份绑定不同)
            with patch.object(sys.modules[__name__], "check_blacklist", side_effect=fake_check):
                got = await _check_all_blacklists(db=_RealDB(), request=req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<18} 命中={sorted(hits) or '无'}  期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # 2. _blacklist_reject 子函数: 返回 RiskCheckResponse
    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="U001")
    resp = _blacklist_reject(req, blocked_by="用户")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  risk_level    = '{resp.risk_level}'")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (P1-S9 新字段, 区分撞的哪种)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    # 3. process_event 主入口: 4 步业务流
    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 order_id = source_id)")
    print("  3. _check_all_blacklists (短路: 用户 > 护照号 > 设备指纹 > IP)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 黑名单拦截是独立 1 步, 审计 noise 0 (不写 risk_event/case)")
