"""
业务实体校验器: 集中处理"用户/订单/售后"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ComplaintClaim,
    InspectionRecord,
    ShipperInfo,
    WaybillInfo,
)
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def ensure_exists(
    db: AsyncSession,
    model: type,
    field_name: str,
    value: Any,
    *,
    entity_label: str,
    field_label: Optional[str] = None,
    cast_value: Optional[Callable[[Any], Any]] = None,
    status_code: int = 404,
) -> None:
    """泛型存在性校验: 检查 model.field_name == value 的记录是否存在."""
    field_label = field_label or f"{entity_label}ID"
    if not value:
        # 空值属于"调用方没传对", 不是"实体不存在", 抛 400
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    compare_value = cast_value(value) if cast_value else value
    stmt = (
        select(func.count())
        .select_from(model)
        .where(getattr(model, field_name) == compare_value)
        .limit(1)
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(
            status_code=status_code,
            detail=f"{field_label}不存在: {value}",
        )


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, ShipperInfo, "shipper_id", user_id, entity_label="卖家")


# 防"水平越权": 拿真运单+假卖家绕过风控
# 攻击场景: 攻击者拿自己的 shipper_id + 别人的真实 waybill_id 调风控
# 后果: 别人的运单被风控/被拒, 业务投诉
async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    owner = (await db.execute(
        select(WaybillInfo.shipper_id).where(WaybillInfo.waybill_id == order_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"运单号不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 运单归属不一致 waybill_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"运单 {order_id} 属于卖家 {owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
# 三段式 10 类事件: 卖家侧/运输侧/退货侧 source_id 都指向运单号; 验货类指向验货记录
_EVENT_SOURCE_VALIDATORS = {
    ("卖家下单寄件", "揽收入仓", "出仓发货", "运输中", "派送中",
     "买家签收", "买家拒收", "买家退回寄件"): (WaybillInfo, "waybill_id", None, "运单", 400),
    ("验货完成", "退货入仓验货"): (InspectionRecord, "record_id", None, "验货记录", 400),
    ("投诉",): (ComplaintClaim, "claim_id", None, "投诉纠纷", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label,
            cast_value=caster,
            status_code=status_code,
        )
        return

    # 兜底: event_type 不在字典里 (Pydantic schema 层 Literal 限定, 实际不会发生,
    # 这里兜底, 防未来加新 event_type 时漏配)
    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


# ============================================================
# Demo: 展示 4 个 ensure_* 函数 + _EVENT_SOURCE_VALIDATORS 字典派发表 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from fastapi import HTTPException

    print("=" * 60)
    print("Service Validator — 4 个 ensure_* + 字典派发表 + 完整校验链")
    print("=" * 60)

    # 1. _EVENT_SOURCE_VALIDATORS 字典派发演示
    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<14} {'model':<16} {'field':<14} {'label':<6} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<14} {model.__name__:<16} {field:<14} {label:<6} {status}")

    # 2. ensure_exists: 用户存在/不存在 的两种行为
    print("\n[2] ensure_exists 行为 (mock DB):")

    class _FakeDB:
        """Mock DB: 模拟 SELECT COUNT(*) -> scalar() 返回 1 或 0"""
        def __init__(self, found):
            self.found = found
        async def execute(self, stmt):
            class _R:
                def __init__(self, n): self.n = n
                def scalar(self):
                    return self.n
            return _R(self.found)

    async def demo_ensure_exists():
        # 存在 → 正常返回
        try:
            await ensure_exists(_FakeDB(found=1), ShipperInfo, "shipper_id", "SHP0001", entity_label="卖家")
            print("  [OK]   shipper_id='SHP0001' 存在 → 不抛异常")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        # 不存在 → 抛 404
        try:
            await ensure_exists(_FakeDB(found=0), ShipperInfo, "shipper_id", "SHP9999", entity_label="卖家")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [404]  shipper_id='SHP9999' 不存在 → {e.detail}  (status={e.status_code})")

    asyncio.run(demo_ensure_exists())

    # 3. ensure_source_matches_event_type: event_type 不匹配 → 400
    print("\n[3] ensure_source_matches_event_type 行为:")
    print("  event_type='卖家下单寄件' 但用验货记录ID当 source_id → 报错 (派发错模型)")

    async def demo_event_dispatch():
        # mock: 同时支持 .scalar() (给 ensure_exists) 和 .scalar_one_or_none() (给 ensure_order_belongs_to_user)
        class _FlexDB:
            def __init__(self, count_n, row):
                self.count_n = count_n
                self.row = row
            async def execute(self, stmt):
                class _R:
                    def __init__(self, n, r): self.n = n; self.r = r
                    def scalar(self): return self.n
                    def scalar_one_or_none(self): return self.r
                return _R(self.count_n, self.row)

        from app.schemas import RiskCheckRequest
        req_ok = RiskCheckRequest(event_type="卖家下单寄件", source_id="WB000001", user_id="SHP0001")
        # count=1 (存在), row 也有 (单条运单)
        try:
            await ensure_source_matches_event_type(_FlexDB(1, SimpleNamespace(waybill_id="WB000001")), req_ok)
            print("  [OK]   event_type=卖家下单寄件 + source_id=WB000001 → WaybillInfo 存在, 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        # 错误配对: 用验货记录ID当 source_id 但 event_type=卖家下单寄件 → 走 WaybillInfo 但查不到
        req_bad = RiskCheckRequest(event_type="卖家下单寄件", source_id="IR0001001", user_id="SHP0001")
        try:
            await ensure_source_matches_event_type(_FlexDB(0, None), req_bad)
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [400]  source_id='IR0001001' 在 WaybillInfo 找不到 → {e.detail[:60]}...  (status={e.status_code})")

    asyncio.run(demo_event_dispatch())

    # 4. ensure_order_belongs_to_user: 防越权
    print("\n[4] ensure_order_belongs_to_user 防越权:")
    print("  shipper_id='SHP0001' 试图操作 waybill_id='WB9999' (属于 SHP0002) → 403")

    async def demo_ownership():
        # mock 直接返回字符串 (因为代码用 select(WaybillInfo.shipper_id) → scalar_one_or_none 拿到的是字符串)
        class _WaybillOwnerSHP0002:
            async def execute(self, stmt):
                class _R:
                    def scalar(self): return 1
                    def scalar_one_or_none(self): return "SHP0002"   # 运单属于别人
                return _R()
        try:
            await ensure_order_belongs_to_user(_WaybillOwnerSHP0002(), "WB9999", "SHP0001")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [403]  {e.detail[:60]}...  (status={e.status_code})")

        # 运单属于本人 → 通过
        class _WaybillOwnerSHP0001:
            async def execute(self, stmt):
                class _R:
                    def scalar(self): return 1
                    def scalar_one_or_none(self): return "SHP0001"   # 运单属于本人
                return _R()
        try:
            await ensure_order_belongs_to_user(_WaybillOwnerSHP0001(), "WB000001", "SHP0001")
            print("  [OK]   waybill_id='WB000001' 属于 SHP0001 → 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

    asyncio.run(demo_ownership())

    print("\n" + "=" * 60)
    print("总结: 4 个 ensure_* 覆盖 '实体存在 + 类型匹配 + 归属' 3 维度校验, 全用 FastAPI HTTPException 兜底")


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 运单类事件: 校验运单归属卖家 (防绕过)
    if request.event_type in ("卖家下单寄件", "揽收入仓", "出仓发货", "运输中",
                              "派送中", "买家签收", "买家拒收", "买家退回寄件"):
        # waybill_id 优先用请求里传的, 没传就用 source_id (业务约定)
        waybill_id = request.order_id or request.source_id
        await ensure_order_belongs_to_user(db, waybill_id, request.user_id)
