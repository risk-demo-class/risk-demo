"""
业务实体校验器: 集中处理"参保人/结算/处方/挂号/药品订单"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    DrugOrder,
    InsuranceClaim,
    Prescription,
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
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="参保人")


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("医保结算",): (InsuranceClaim, "claim_id", None, "医保结算单", 400),
    ("处方审核",): (Prescription, "rx_id", None, "处方单", 400),
    ("挂号",): (Appointment, "appt_id", None, "挂号单", 400),
    ("药品代购",): (DrugOrder, "drug_order_id", None, "药品订单", 400),
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


# 防"水平越权": 拿真业务单 + 假用户绕过风控
async def ensure_business_belongs_to_user(
    db: AsyncSession,
    model: type,
    id_field: str,
    business_id: str,
    user_id: str,
) -> None:
    owner = (await db.execute(
        select(getattr(model, "user_id")).where(getattr(model, id_field) == business_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"业务单ID不存在: {business_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 业务单归属不一致 id=%s, owner=%s, request_user=%s",
            business_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"业务单 {business_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 参保人存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 业务单归属校验 (防绕过: 用别人的结算单/处方/挂号/药品订单)
    for event_types, (model, field, _, _, _) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type in event_types:
            await ensure_business_belongs_to_user(
                db, model, field, request.source_id, request.user_id,
            )
            return


# ============================================================
# Demo: 展示校验器 + 字典派发表 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from fastapi import HTTPException

    print("=" * 60)
    print("Service Validator — 4 个医疗事件 + 字典派发表 + 归属校验")
    print("=" * 60)

    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<12} {'model':<16} {'field':<16} {'label':<8} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<12} {model.__name__:<16} {field:<16} {label:<8} {status}")

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
            await ensure_exists(_FakeDB(found=1), UserInfo, "user_id", "U001", entity_label="参保人")
            print("  [OK]   user_id='U001' 存在 → 不抛异常")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")
        try:
            await ensure_exists(_FakeDB(found=0), UserInfo, "user_id", "U999", entity_label="参保人")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [404]  user_id='U999' 不存在 → {e.detail}  (status={e.status_code})")

    asyncio.run(demo_ensure_exists())

    print("\n[3] ensure_business_belongs_to_user 防越权:")
    async def demo_ownership():
        class _OwnerU002:
            async def execute(self, stmt):
                class _R:
                    def scalar(self):
                        return 1
                    def scalar_one_or_none(self):
                        return "U002"
                return _R()
        try:
            await ensure_business_belongs_to_user(_OwnerU002(), InsuranceClaim, "claim_id", "CLM999", "U001")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [403]  {e.detail[:60]}...  (status={e.status_code})")

        class _OwnerU001:
            async def execute(self, stmt):
                class _R:
                    def scalar(self):
                        return 1
                    def scalar_one_or_none(self):
                        return "U001"
                return _R()
        try:
            await ensure_business_belongs_to_user(_OwnerU001(), InsuranceClaim, "claim_id", "CLM001", "U001")
            print("  [OK]   claim_id='CLM001' 属于 U001 → 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

    asyncio.run(demo_ownership())

    print("\n" + "=" * 60)
    print("总结: 4 个医疗事件 (医保结算/处方审核/挂号/药品代购) 的实体存在 + 归属校验")