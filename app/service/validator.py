"""
制造业业务实体校验器: 集中处理"经销商/订货单/保修工单/串货举报"等业务实体的
存在性、一致性校验. 所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrossRegionReport, OrderInfo, UserInfo, WarrantyRecord
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
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


# 防"水平越权": 拿真订单+假经销商绕过风控
async def ensure_order_belongs_to_dealer(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    owner = (await db.execute(
        select(OrderInfo.dealer_id).where(OrderInfo.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"订货单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订货单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订货单 {order_id} 属于经销商 {owner}, 与请求用户 {user_id} 不一致",
        )


async def ensure_warranty_belongs_to_dealer(
    db: AsyncSession,
    warranty_id: str,
    user_id: str,
) -> None:
    """保修/维修工单归属校验: 工单 → 订货单 → dealer_id 必须等于请求用户."""
    row = (await db.execute(
        select(OrderInfo.dealer_id)
        .select_from(WarrantyRecord)
        .join(OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id)
        .where(WarrantyRecord.warranty_id == warranty_id)
        .limit(1)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"保修工单ID不存在: {warranty_id}")
    if row != user_id:
        logger.warning(
            "安全告警: 保修工单归属不一致 warranty_id=%s, owner=%s, request_user=%s",
            warranty_id, row, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"保修工单 {warranty_id} 属于经销商 {row}, 与请求用户 {user_id} 不一致",
        )


async def ensure_report_belongs_to_dealer(
    db: AsyncSession,
    report_id: str,
    user_id: str,
) -> None:
    """串货举报归属校验: 风控对象是被举报经销商, user_id 必须等于 report.dealer_id."""
    owner = (await db.execute(
        select(CrossRegionReport.dealer_id)
        .where(CrossRegionReport.report_id == int(report_id))
        .limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"串货举报单ID不存在: {report_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 串货举报归属不一致 report_id=%s, owner=%s, request_user=%s",
            report_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"串货举报单 {report_id} 针对经销商 {owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("经销商订货", "采购订单"): (OrderInfo, "order_id", None, "订货单", 400),
    ("保修申请", "售后维修"): (WarrantyRecord, "warranty_id", None, "保修工单", 400),
    ("串货举报",): (CrossRegionReport, "report_id", int, "串货举报单", 400),
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

    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """组合校验: 用户存在 + source_id 与事件类型匹配 + 业务归属 (防越权)."""
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 归属校验 (user_id 必须是业务主体)
    if request.event_type in ("经销商订货", "采购订单"):
        order_id = request.order_id or request.source_id
        await ensure_order_belongs_to_dealer(db, order_id, request.user_id)
    elif request.event_type in ("保修申请", "售后维修"):
        await ensure_warranty_belongs_to_dealer(db, request.source_id, request.user_id)
    elif request.event_type == "串货举报":
        await ensure_report_belongs_to_dealer(db, request.source_id, request.user_id)


# ============================================================
# Demo: 展示 3 类事件派发 + 3 个归属校验 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Service Validator — 制造业字典派发表 + 归属校验链")
    print("=" * 60)

    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<14} {'model':<18} {'field':<14} {'label':<8} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<14} {model.__name__:<18} {field:<14} {label:<8} {status}")

    print("\n[2] 归属校验演示 (mock):")

    class _FakeDB:
        """Mock DB: scalar_one_or_none 返回 owner"""
        def __init__(self, owner):
            self.owner = owner
        async def execute(self, stmt):
            class _R:
                def __init__(self, o):
                    self.o = o
                def scalar(self):
                    return 1 if self.o else 0
                def scalar_one_or_none(self):
                    return self.o
            return _R(self.owner)

    async def demo():
        # 归属一致 → 通过
        try:
            await ensure_order_belongs_to_dealer(_FakeDB("D001"), "ORD001", "D001")
            print("  [OK]   经销商 D001 的 ORD001 → 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")
        # 归属不一致 → 403
        try:
            await ensure_order_belongs_to_dealer(_FakeDB("D002"), "ORD001", "D001")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [403]  D001 操作 D002 的订单 → {e.detail[:50]}...")

    asyncio.run(demo())

    print("\n" + "=" * 60)
    print("总结: ensure_* 覆盖 '实体存在 + 事件类型匹配 + 经销商归属' 3 维度校验")
