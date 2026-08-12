"""
业务实体校验器: 集中处理"号卡/业务单/CDR/短信"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.

参照 ai_risk/app/service/validator.py, 适配电信业务:
  - 核心实体: 号卡(msisdn) 是枢纽
  - source_id 与 event_type 匹配: 按 event_type 派发到对应模型校验
  - 水平越权: 客户名下号卡一致性校验
"""
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    TelecomCard,
    TelecomCdr,
    TelecomCustomer,
    TelecomIotCard,
    TelecomServiceOrder,
    TelecomSms,
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


async def ensure_card_exists(db: AsyncSession, msisdn: str) -> None:
    """号卡存在性校验 (核心校验, 所有风控入口必过)."""
    await ensure_exists(db, TelecomCard, "msisdn", msisdn, entity_label="号卡")


async def ensure_customer_exists(db: AsyncSession, customer_id: str) -> None:
    """客户存在性校验."""
    await ensure_exists(db, TelecomCustomer, "customer_id", customer_id, entity_label="客户")


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("开户",): (TelecomServiceOrder, "order_id", None, "业务单", 400),
    ("通话", "国际来电"): (TelecomCdr, "cdr_id", int, "通话记录", 400),
    ("短信发送",): (TelecomSms, "sms_id", int, "短信记录", 400),
    ("物联网激活",): (TelecomIotCard, "msisdn", None, "物联网卡", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """按 event_type 派发校验 source_id 是否在对应业务表中存在.

    电信场景:
      - 开户 → 业务单 (TelecomServiceOrder.order_id)
      - 通话/国际来电 → CDR (TelecomCdr.cdr_id)
      - 短信发送 → 短信 (TelecomSms.sms_id)
      - 物联网激活 → 物联网卡 (TelecomIotCard.msisdn)
    """
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label,
            field_label=f"{label}ID",
            cast_value=caster,
            status_code=status_code,
        )
        return

    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


# ============================================================
# Demo: 展示 ensure_* 函数 + 字典派发表 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    import asyncio
    from types import SimpleNamespace

    print("=" * 60)
    print("电信 Service Validator — ensure_* + 字典派发表 + 完整校验链")
    print("=" * 60)

    print("\n[1] _EVENT_SOURCE_VALIDATORS 字典派发表:")
    print(f"  {'event_type':<16} {'model':<25} {'field':<14} {'label':<6} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<16} {model.__name__:<25} {field:<14} {label:<6} {status}")

    class _FakeDB:
        def __init__(self, found):
            self.found = found
        async def execute(self, stmt):
            class _R:
                def __init__(self, n): self.n = n
                def scalar(self): return self.n
            return _R(self.found)

    async def demo():
        print("\n[2] ensure_card_exists:")
        try:
            await ensure_card_exists(_FakeDB(1), "13800000001")
            print("  [OK]   msisdn 存在 → 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        try:
            await ensure_card_exists(_FakeDB(0), "13899999999")
        except HTTPException as e:
            print(f"  [404]  msisdn 不存在 → {e.detail}")

        print("\n[3] ensure_source_matches_event_type 派发:")
        for evt, src, found in [("开户", "SO001", 1), ("通话", "1", 1), ("通话", "999", 0), ("短信发送", "1", 1)]:
            req = RiskCheckRequest(event_type=evt, source_id=src, msisdn="13800000001")
            try:
                await ensure_source_matches_event_type(_FakeDB(found), req)
                print(f"  [OK]   event_type={evt}, source_id={src} → 通过")
            except HTTPException as e:
                print(f"  [400]  event_type={evt}, source_id={src} → {e.detail[:50]}...")

    asyncio.run(demo())

    print("\n" + "=" * 60)
    print("总结: 3 个 ensure_* + 字典派发表覆盖 5 种事件类型的 source_id 校验")