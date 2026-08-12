"""
物流行业风控系统 - 业务实体校验器
处理 寄件人、运单、实名认证 等实体的存在性与归属校验
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Shipment,
    UserInfo,
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
    """泛型存在性校验: 检查 model.field_name == value 的记录是否存在"""
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


async def ensure_shipment_belongs_to_sender(
    db: AsyncSession,
    shipment_id: str,
    sender_id: str,
) -> None:
    """防越权: 校验运单归属 (运单必须属于寄件人)."""
    owner = (await db.execute(
        select(Shipment.sender_id).where(Shipment.shipment_id == shipment_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"运单ID不存在: {shipment_id}")
    if owner != sender_id:
        logger.warning(
            "安全告警: 运单归属不一致 shipment_id=%s, owner=%s, request_user=%s",
            shipment_id, owner, sender_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"运单 {shipment_id} 属于用户 {owner}, 与请求用户 {sender_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则
_EVENT_SOURCE_VALIDATORS = {
    ("shipment_create", "shipment_cancel", "shipment_receive"): (Shipment, "shipment_id", None, "运单", 400),
    ("id_verification",): (UserInfo, "user_id", None, "用户", 400),
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
    # 1. 用户存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 运单场景: 校验寄件人归属 (防越权)
    if request.event_type in ("shipment_create", "shipment_cancel"):
        await ensure_shipment_belongs_to_sender(db, request.source_id, request.user_id)


# ============================================================
# Demo: 展示 4 个 ensure_* 校验函数 (无 DB 依赖, 纯 print)
# 运行方式: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Validator - 4 个 ensure_* 校验函数")
    print("=" * 60)
    print("  1. ensure_exists                      (泛型存在性校验)")
    print("  2. ensure_user_exists                 (用户存在)")
    print("  3. ensure_shipment_belongs_to_sender  (运单归属防越权)")
    print("  4. ensure_source_matches_event_type   (事件类型派发表)")
    print()
    print("事件类型 -> source 表映射:")
    for ets, (model, field, caster, label, _) in _EVENT_SOURCE_VALIDATORS.items():
        print(f"  {list(ets)} -> {model.__tablename__}.{field} ({label})")
    print("=" * 60)
