"""
业务实体校验器: 集中处理"用户/经销商/订单/保修单/举报单"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
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
        raise HTTPException(status_code=404, detail=f"订单ID不存在: {order_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 订单归属不一致 order_id=%s, owner=%s, request_user=%s",
            order_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"订单 {order_id} 属于经销商 {owner}, 与请求用户 {user_id} 不一致",
        )


# 保修/维修事件: 保修单必须属于该经销商 (订单归属校验)
async def ensure_warranty_belongs_to_dealer(
    db: AsyncSession,
    warranty_id: str,
    user_id: str,
) -> None:
    owner = (await db.execute(
        select(WarrantyRecord.order_id).where(WarrantyRecord.warranty_id == warranty_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"保修单ID不存在: {warranty_id}")
    order_owner = (await db.execute(
        select(OrderInfo.dealer_id).where(OrderInfo.order_id == owner).limit(1)
    )).scalar_one_or_none()
    if not order_owner:
        raise HTTPException(status_code=404, detail=f"保修单关联订单不存在: {owner}")
    if order_owner != user_id:
        logger.warning(
            "安全告警: 保修单归属不一致 warranty_id=%s, owner=%s, request_user=%s",
            warranty_id, order_owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"保修单 {warranty_id} 属于经销商 {order_owner}, 与请求用户 {user_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("经销商订货",): (OrderInfo, "order_id", None, "订单", 400),
    ("保修申请", "售后维修"): (WarrantyRecord, "warranty_id", None, "保修单", 400),
    ("串货举报",): (CrossRegionReport, "report_id", None, "举报单", 400),
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


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 归属校验 (防越权)
    if request.event_type == "经销商订货":
        order_id = request.order_id or request.source_id
        await ensure_order_belongs_to_dealer(db, order_id, request.user_id)
    elif request.event_type in ("保修申请", "售后维修"):
        await ensure_warranty_belongs_to_dealer(db, request.source_id, request.user_id)
    # 串货举报: 举报人是谁都行 (reporter_id 是业务侧填的, 不强制归属)
