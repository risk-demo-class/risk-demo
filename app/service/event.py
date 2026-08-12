"""
事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (用户/包裹/危险品申报/COD结算 是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (parcel_id, receiver_id)
  3. 黑名单前置拦截 (用户/地址/手机号 3 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

【物流版改造】以"物"(包裹/收件人) 为核心:
  - 电商"订单" → 物流"包裹" Parcel
  - 寄件人 SenderInfo + 收件人 ReceiverInfo 双向风险对象
  - 4 类物流事件 source_id 语义:
      parcel_pickup 揽收 / cross_border_ship 跨境发运: source_id = parcel_id
      dangerous_declare 危险品申报: source_id = decl_id → 反查 parcel_id
      cod_settlement COD 结算: source_id = cod_id → 反查 parcel_id
  - 黑名单预检覆盖: 寄件用户 + 寄件手机号 + 收件手机号 + 收件地址 (双端)
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    CodTransaction,
    DangerousDeclaration,
    Parcel,
    ReceiverInfo,
    SenderInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验 (validator.py: 实体存在 + source_id 类型匹配 + 包裹归属)
    await validate_risk_check_request(db, request)

    # 2. 补全 parcel_id / receiver_id (黑名单检查需要 receiver_id)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s, parcel_id=%s",
                       blocked, request.user_id, getattr(request, "parcel_id", None))
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 地址 > 手机号; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    # 1. 寄件用户黑名单: 必查
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 地址黑名单: 收件地址 (有 receiver_id 时反查 ReceiverInfo.address)
    if request.receiver_id:
        row = (await db.execute(
            select(ReceiverInfo.address).where(ReceiverInfo.receiver_id == request.receiver_id)
        )).first()
        if row and row.address and await check_blacklist(db, "地址", row.address):
            return "地址"

    # 3. 手机号黑名单: 寄件手机号 (sender_id=user_id 约定) + 收件手机号
    sender_row = (await db.execute(
        select(SenderInfo.phone).where(SenderInfo.sender_id == request.user_id)
    )).first()
    if sender_row and sender_row.phone and await check_blacklist(db, "手机号", sender_row.phone):
        return "手机号"

    if request.receiver_id:
        receiver_row = (await db.execute(
            select(ReceiverInfo.phone).where(ReceiverInfo.receiver_id == request.receiver_id)
        )).first()
        if receiver_row and receiver_row.phone and await check_blacklist(db, "手机号", receiver_row.phone):
            return "手机号"

    return None


# 按 event_type 自动补全 parcel_id / receiver_id
# if/elif 不用字典派发: SQL 差异大, if/elif 更易读
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type in ("parcel_pickup", "cross_border_ship"):
        # source_id 就是 parcel_id, 不需要反查
        if not request.parcel_id:
            request.parcel_id = request.source_id
        if not request.receiver_id and request.parcel_id:
            request.receiver_id = await _resolve_receiver_id(db, request.parcel_id)

    elif request.event_type == "dangerous_declare":
        # source_id 是 decl_id → 反查 parcel_id → 再反查 receiver_id
        if not request.parcel_id and request.source_id:
            request.parcel_id = await _resolve_parcel_id(
                db, DangerousDeclaration, DangerousDeclaration.parcel_id,
                DangerousDeclaration.decl_id, request.source_id,
            )
        if not request.receiver_id and request.parcel_id:
            request.receiver_id = await _resolve_receiver_id(db, request.parcel_id)

    elif request.event_type == "cod_settlement":
        # source_id 是 cod_id → 反查 parcel_id → 再反查 receiver_id
        if not request.parcel_id and request.source_id:
            request.parcel_id = await _resolve_parcel_id(
                db, CodTransaction, CodTransaction.parcel_id,
                CodTransaction.cod_id, request.source_id,
            )
        if not request.receiver_id and request.parcel_id:
            request.receiver_id = await _resolve_receiver_id(db, request.parcel_id)

    # 电商旧事件 (下单/支付/售后申请/物流投诉): 无对应物流业务表, 跳过补全
    # (增量兼容保留, source_id 语义不变, 由 decision.py 旧逻辑处理)

    return request


async def _resolve_receiver_id(db: AsyncSession, parcel_id: str) -> str | None:
    """按 parcel_id 反查收件人 receiver_id."""
    row = (await db.execute(
        select(Parcel.receiver_id).where(Parcel.parcel_id == parcel_id)
    )).first()
    return row.receiver_id if row else None


async def _resolve_parcel_id(
    db: AsyncSession, model: type, parcel_field, key_field, key_value: str,
) -> str | None:
    """按业务表主键 (decl_id/cod_id) 反查 parcel_id."""
    row = (await db.execute(
        select(parcel_field).where(key_field == key_value)
    )).first()
    return row[0] if row else None


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
# Demo: _check_all_blacklists 黑名单优先级短路 + _enrich_request 事件补全 — mock DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event — 物流版: 黑名单短路 + 事件补全")
    print("=" * 60)

    # 1. _check_all_blacklists 子函数: 用户 > 地址 > 手机号 (双端)
    print("\n[1] 黑名单检查优先级: 用户 → 收件地址 → 寄件手机号 → 收件手机号 (短路)")

    async def demo_blacklist_priority():
        scenarios = [
            ("只用户撞黑",     ["用户", None, None, None],  "用户"),
            ("只地址撞黑",     [None, "地址", None, None],  "地址"),
            ("用户+地址都撞",  ["用户", "地址", None, None], "用户"),
            ("寄件手机号撞黑", [None, None, "手机号", None], "手机号"),
            ("全没撞",         [None, None, None, None],   None),
        ]
        for name, hits, expected in scenarios:
            seq = iter(hits)

            # monkeypatch 模块级 check_blacklist: 按"撞哪种类型"脚本序列返回
            # 注意: -m 运行时模块 __name__ == "__main__", 不能 import 同名模块再 patch,
            #       直接用 globals() 替换当前模块的全局名
            async def fake_check_blacklist(db, blacklist_type, value):
                try:
                    return next(seq) == blacklist_type
                except StopIteration:
                    return False

            # fake DB: 地址/手机号查询返回真实值, 黑名单表走 monkeypatch
            class _FlexDB:
                async def execute(self, stmt):
                    class _R:
                        def __init__(self, r): self.r = r
                        def first(self): return self.r
                        # check_blacklist 用 scalar_one_or_none (此处已被 monkeypatch, 不会走到)
                        def scalar_one_or_none(self): return self.r
                    s = str(stmt)
                    if "receiver_info" in s:
                        return _R(SimpleNamespace(address="上海测试路1号", phone="13900002222"))
                    if "sender_info" in s:
                        return _R(SimpleNamespace(phone="13800001111"))
                    return _R(None)

            orig = globals()["check_blacklist"]
            globals()["check_blacklist"] = fake_check_blacklist
            try:
                req = SimpleNamespace(user_id="U0001", parcel_id="P000001", receiver_id="R0001")
                got = await _check_all_blacklists(_FlexDB(), req)
            finally:
                globals()["check_blacklist"] = orig
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<22} 命中序列={hits}  期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # 2. _enrich_request 事件补全: 4 类物流事件
    print("\n[2] _enrich_request 事件补全 (parcel_id / receiver_id):")

    async def demo_enrich():
        # mock DB: 按 SQL 区分两类查询
        #   - "receiver_id" 列 → 返回命名空间 (row.receiver_id 属性取)
        #   - 其他 (dangerous_declaration/cod_transaction 的 parcel_id 列) → 返回 1 元组 (row[0] 下标取)
        class _FlexDB:
            def __init__(self, parcel_id, receiver_id):
                self.parcel_id = parcel_id
                self.receiver_id = receiver_id
            async def execute(self, stmt):
                class _R:
                    def __init__(self, r): self.r = r
                    def first(self): return self.r
                s = str(stmt)
                if "receiver_id" in s:
                    return _R(SimpleNamespace(receiver_id=self.receiver_id))
                return _R((self.parcel_id,))

        # 场景 1: parcel_pickup, source_id=P000001 → parcel_id 直接用, receiver_id 反查
        db = _FlexDB(None, "R0001")
        req = RiskCheckRequest(event_type="parcel_pickup", source_id="P000001", user_id="U0001")
        out = await _enrich_request(db, req)
        print(f"  parcel_pickup:   parcel_id={out.parcel_id:<8} receiver_id={out.receiver_id}")

        # 场景 2: dangerous_declare, source_id=DCL00001 → 反查 parcel_id → 反查 receiver_id
        db = _FlexDB("P000003", "R0003")
        req = RiskCheckRequest(event_type="dangerous_declare", source_id="DCL00001", user_id="U0001")
        out = await _enrich_request(db, req)
        print(f"  dangerous_declare: parcel_id={out.parcel_id:<8} receiver_id={out.receiver_id}")

        # 场景 3: cod_settlement, source_id=COD00001 → 反查 parcel_id → 反查 receiver_id
        db = _FlexDB("P000005", "R0005")
        req = RiskCheckRequest(event_type="cod_settlement", source_id="COD00001", user_id="U0001")
        out = await _enrich_request(db, req)
        print(f"  cod_settlement:   parcel_id={out.parcel_id:<8} receiver_id={out.receiver_id}")

        # 场景 4: 电商旧事件 → 跳过补全
        db = _FlexDB(None, None)
        req = RiskCheckRequest(event_type="下单", source_id="whatever", user_id="U0001")
        out = await _enrich_request(db, req)
        print(f"  下单(旧事件):    parcel_id={out.parcel_id}  (保持 None, 跳过)")

    asyncio.run(demo_enrich())

    # 3. _blacklist_reject 子函数: 返回 RiskCheckResponse
    print("\n[3] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="U0001")
    resp = _blacklist_reject(req, blocked_by="地址")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (区分撞的哪种)")

    # 4. process_event 主入口: 4 步业务流
    print("\n[4] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py: 实体存在 + 类型匹配 + 归属)")
    print("  2. _enrich_request (补全 parcel_id / receiver_id)")
    print("  3. _check_all_blacklists (短路: 用户 > 地址 > 手机号, 寄收双端)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 物流版黑名单拦截覆盖寄收双端, 事件补全支持 decl_id/cod_id 反查 parcel")
