"""
制造业风控系统 - 业务实体校验器
集中处理"经销商用户 / 订货订单 / 保修单 / 串货举报"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CrossRegionReport,
    OrderInfo,
    UserInfo,
    WarrantyRecord,
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
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="经销商用户")


async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    """防"水平越权": 订单 dealer_id 必须与请求用户 user_id 一致 (经销商账号即 dealer_id)."""
    owner = (await db.execute(
        select(OrderInfo.dealer_id).where(OrderInfo.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"订货订单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订单 {order_id} 属于经销商 {owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("经销商订货",): (OrderInfo, "order_id", None, "订货订单", 400),
    ("设备保修",): (WarrantyRecord, "warranty_id", None, "保修单", 400),
    ("跨区串货举报",): (CrossRegionReport, "report_id", None, "举报记录", 400),
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

    # 兜底: event_type 不在字典里 (Pydantic schema 层 Literal 限定, 实际不会发生)
    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


# ============================================================
# Demo: 展示 3 个 ensure_* 函数 + _EVENT_SOURCE_VALIDATORS 字典派发表 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from fastapi import HTTPException

    print("=" * 60)
    print("Service Validator — 3 个 ensure_* + 字典派发表 + 完整校验链")
    print("=" * 60)

    # 1. _EVENT_SOURCE_VALIDATORS 字典派发演示
    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<14} {'model':<20} {'field':<14} {'label':<8} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<14} {model.__name__:<20} {field:<14} {label:<8} {status}")

    # 2. ensure_exists: 存在/不存在 两种行为
    print("\n[2] ensure_exists 行为 (mock DB):")

    class _FakeDB:
        def __init__(self, found):
            self.found = found
        async def execute(self, stmt):
            class _R:
                def __init__(self, n):
                    self.n = n
                def scalar(self):
                    return self.n
            return _R(self.found)

    async def demo_ensure_exists():
        try:
            await ensure_exists(_FakeDB(found=1), UserInfo, "user_id", "D001", entity_label="经销商用户")
            print("  [OK]   user_id='D001' 存在 → 不抛异常")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        try:
            await ensure_exists(_FakeDB(found=0), UserInfo, "user_id", "D999", entity_label="经销商用户")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [404]  user_id='D999' 不存在 → {e.detail}  (status={e.status_code})")

    asyncio.run(demo_ensure_exists())

    # 3. ensure_source_matches_event_type: event_type 不匹配 → 400
    print("\n[3] ensure_source_matches_event_type 行为:")
    print("  event_type='经销商订货' 但用 warranty_id 当 source_id → 报错 (派发错模型)")

    async def demo_event_dispatch():
        class _FlexDB:
            def __init__(self, count_n, row):
                self.count_n = count_n
                self.row = row
            async def execute(self, stmt):
                class _R:
                    def __init__(self, n, r):
                        self.n = n
                        self.r = r
                    def scalar(self):
                        return self.n
                    def scalar_one_or_none(self):
                        return self.r
                return _R(self.count_n, self.row)

        from app.schemas import RiskCheckRequest
        req_ok = RiskCheckRequest(event_type="经销商订货", source_id="ORD001", user_id="D001")
        try:
            await ensure_source_matches_event_type(_FlexDB(1, SimpleNamespace(dealer_id="D001")), req_ok)
            print("  [OK]   event_type=经销商订货 + source_id=ORD001 → OrderInfo 存在, 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        req_bad = RiskCheckRequest(event_type="经销商订货", source_id="WR001", user_id="D001")
        try:
            await ensure_source_matches_event_type(_FlexDB(0, None), req_bad)
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [400]  source_id='WR001' 在 OrderInfo 找不到 → {e.detail[:60]}...  (status={e.status_code})")

    asyncio.run(demo_event_dispatch())

    # 4. ensure_order_belongs_to_user: 防越权
    print("\n[4] ensure_order_belongs_to_user 防越权:")
    print("  user_id='D001' 试图操作 order_id='ORD999' (属于 D002) → 403")

    async def demo_ownership():
        class _OrderOwnerD002:
            async def execute(self, stmt):
                class _R:
                    def scalar(self):
                        return 1
                    def scalar_one_or_none(self):
                        return "D002"
                return _R()
        try:
            await ensure_order_belongs_to_user(_OrderOwnerD002(), "ORD999", "D001")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [403]  {e.detail[:60]}...  (status={e.status_code})")

        class _OrderOwnerD001:
            async def execute(self, stmt):
                class _R:
                    def scalar(self):
                        return 1
                    def scalar_one_or_none(self):
                        return "D001"
                return _R()
        try:
            await ensure_order_belongs_to_user(_OrderOwnerD001(), "ORD001", "D001")
            print("  [OK]   order_id='ORD001' 属于 D001 → 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

    asyncio.run(demo_ownership())

    print("\n" + "=" * 60)
    print("总结: 3 个 ensure_* 覆盖 '实体存在 + 类型匹配 + 归属' 3 维度校验, 全用 FastAPI HTTPException 兜底")


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 经销商用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 经销商订货/设备保修场景: 校验订单归属 (防绕过)
    if request.event_type in ("经销商订货", "设备保修"):
        order_id = request.order_id or request.source_id
        # 设备保修事件: 订单从保修单反查
        if request.event_type == "设备保修":
            row = (await db.execute(
                select(WarrantyRecord.order_id).where(
                    WarrantyRecord.warranty_id == request.source_id
                )
            )).scalar_one_or_none()
            if row:
                order_id = row
        await ensure_order_belongs_to_user(db, order_id, request.user_id)
