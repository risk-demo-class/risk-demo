"""
业务实体校验器: 集中处理"用户/订单/退改/签证"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.

旅游版派发表 (对应 4 种业务事件):
  预订下单 / 支付   → OrderInfo.order_id
  退改申请          → OrderRefund.refund_id
  签证申请          → VisaApplication.visa_id
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BUSINESS_ORDER_EVENTS, BUSINESS_REFUND_EVENT, BUSINESS_VISA_EVENT
from app.models import (
    OrderInfo,
    OrderRefund,
    UserInfo,
    VisaApplication,
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
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


# 防"水平越权": 拿真订单+假用户绕过风控
async def ensure_order_belongs_to_user(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> None:
    owner = (await db.execute(
        select(OrderInfo.user_id).where(OrderInfo.order_id == order_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"订单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订单 {order_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    BUSINESS_ORDER_EVENTS: (OrderInfo, "order_id", None, "订单", 400),
    (BUSINESS_REFUND_EVENT,): (OrderRefund, "refund_id", None, "退改单", 400),
    (BUSINESS_VISA_EVENT,): (VisaApplication, "visa_id", None, "签证申请", 400),
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


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 订单归属校验 (防绕过): 预订下单/支付 直接校验; 退改申请 从退改单取订单校验
    if request.event_type in BUSINESS_ORDER_EVENTS:
        order_id = request.order_id or request.source_id
        await ensure_order_belongs_to_user(db, order_id, request.user_id)
    elif request.event_type == BUSINESS_REFUND_EVENT:
        row = (await db.execute(
            select(OrderRefund.order_id).where(OrderRefund.refund_id == request.source_id)
        )).first()
        if row and row.order_id:
            await ensure_order_belongs_to_user(db, row.order_id, request.user_id)


# ============================================================
# Demo: 展示 3 个事件类型的派发表 — 无需 DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Service Validator — 旅游事件派发表")
    print("=" * 60)
    print(f"  {'event_type':<14} {'model':<16} {'field':<10} {'label':<6} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<14} {model.__name__:<16} {field:<10} {label:<6} {status}")
    print("\n覆盖: 预订下单/支付 → 订单 | 退改申请 → 退改单 | 签证申请 → 签证申请")
