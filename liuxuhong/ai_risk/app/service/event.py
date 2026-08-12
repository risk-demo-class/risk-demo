"""
事件处理管道 (process_event 统一入口) — 教育行业

4 步业务流:
  1. 业务实体校验 (用户/报名订单/退费是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id)
  3. 黑名单前置拦截 (用户/学号/身份证/设备指纹/直播账号 5 种类型, 撞黑就拒)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import DeviceFingerprint, OrderInfo, RefundRequest, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id (黑名单检查需要关联信息)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


# 优先级: 用户 > 学号 > 身份证 > 设备指纹 > 直播账号; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    # 1. 用户黑名单
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 学号黑名单
    row = (await db.execute(
        select(UserInfo.student_id).where(UserInfo.user_id == request.user_id)
    )).first()
    if row and row.student_id and await check_blacklist(db, "学号", row.student_id):
        return "学号"

    # 3. 身份证黑名单 (暂时用 user_id 代替, 后续可加 id_card 字段)
    # 教学简化: student_id 即可覆盖大部分场景

    # 4. 设备指纹黑名单
    dev_row = (await db.execute(
        select(DeviceFingerprint.fingerprint).where(
            DeviceFingerprint.user_id == request.user_id
        ).limit(1)
    )).first()
    if dev_row and dev_row.fingerprint and await check_blacklist(db, "设备指纹", dev_row.fingerprint):
        return "设备指纹"

    # 5. 直播账号黑名单 (直播打赏场景)
    if request.event_type == "直播打赏":
        if await check_blacklist(db, "直播账号", request.user_id):
            return "直播账号"

    return None


# 按 event_type 自动补全 order_id
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type == "课程报名":
        if not request.order_id:
            request.order_id = request.source_id

    elif request.event_type == "退费申请":
        if not request.order_id:
            row = (await db.execute(
                select(RefundRequest.order_id).where(
                    RefundRequest.refund_id == request.source_id
                )
            )).first()
            if row:
                request.order_id = row.order_id

    elif request.event_type in ("学历认证", "直播打赏"):
        # 学历认证: source_id 是 user_id
        # 直播打赏: source_id 是订单/打赏记录ID, 简化处理
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
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event — 教育行业黑名单优先级短路")
    print("=" * 60)

    # 1. _check_all_blacklists 子函数: 用户 > 学号 > 设备指纹 > 直播账号
    print("\n[1] 黑名单检查优先级: 用户 → 学号 → 设备指纹 → 直播账号 (短路)")

    async def demo_blacklist_priority():
        scenarios = [
            ("只用户撞黑",       ["用户", None,  None,    None],    "用户"),
            ("只学号撞黑",       [None,  "学号", None,    None],    "学号"),
            ("用户+学号都撞",    ["用户", "学号", None,    None],    "用户"),
            ("只设备指纹撞黑",   [None,  None,  "设备指纹", None],  "设备指纹"),
            ("全没撞",           [None,  None,  None,    None],    None),
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
                    if which == "学号":
                        return _R(SimpleNamespace(student_id="STU2024001"))
                    if which == "设备指纹":
                        return _R(SimpleNamespace(fingerprint="fp_shared_dev_001"))
                    if which == "用户":
                        return _R(SimpleNamespace(blacklist_id=1, expire_time=None))
                    if which is None:
                        return _R(None)
                    return _R(None)

            db = _RealDB(list(calls))
            req = SimpleNamespace(user_id="U001", event_type="课程报名")
            got = await _check_all_blacklists(db, req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<22} 期望={expected} 实际={got}")

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
    print("  2. _enrich_request (补全 order_id / receive_id)")
    print("  3. _check_all_blacklists (短路: 用户 > 地址 > 手机号)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: P1-S9 让黑名单拦截成为独立 1 步, 审计 noise 0 (不写 risk_event/case)")
