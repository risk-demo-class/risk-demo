"""
业务实体校验器 (医疗版): 集中处理"患者/挂号/处方/结算/药品订单"等业务实体的
存在性、一致性校验. 所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
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
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="患者")


# 防"水平越权": 拿真单据+假患者绕过风控
# 攻击场景: 攻击者拿自己的 user_id + 别人的真实 rx_id/claim_id 调风控
# 后果: 别人的诊疗单据被风控/被拒, 业务投诉
async def ensure_document_belongs_to_user(
    db: AsyncSession,
    source_id: str,
    user_id: str,
    event_type: str,
) -> None:
    """诊疗单据归属校验: source_id 对应单据的 user_id 必须等于请求的 user_id."""
    owner_map = {
        "挂号": (Appointment, Appointment.appt_id, "挂号记录"),
        "处方开具": (Prescription, Prescription.rx_id, "处方单"),
        "医保结算": (InsuranceClaim, InsuranceClaim.claim_id, "结算单"),
        "药品下单": (DrugOrder, DrugOrder.drug_order_id, "药品订单"),
    }
    entry = owner_map.get(event_type)
    if not entry:
        return
    model, pk_col, label = entry
    owner = (await db.execute(
        select(model.user_id).where(pk_col == source_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"{label}ID不存在: {source_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: 单据归属不一致 event_type=%s, source_id=%s, owner=%s, request_user=%s",
            event_type, source_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"{label} {source_id} 属于患者 {owner}, 与请求患者 {user_id} 不一致",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("挂号",): (Appointment, "appt_id", None, "挂号记录", 400),
    ("处方开具",): (Prescription, "rx_id", None, "处方单", 400),
    ("医保结算",): (InsuranceClaim, "claim_id", None, "结算单", 400),
    ("药品下单",): (DrugOrder, "drug_order_id", None, "药品订单", 400),
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


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 患者存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 单据归属校验 (防越权, 4 种事件都查)
    await ensure_document_belongs_to_user(
        db, request.source_id, request.user_id, request.event_type,
    )


# ============================================================
# Demo: 展示派发表 + ensure_exists 行为 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    from fastapi import HTTPException

    print("=" * 60)
    print("Service Validator (医疗版) — 字典派发表 + 校验链")
    print("=" * 60)

    # 1. _EVENT_SOURCE_VALIDATORS 字典派发
    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<12} {'model':<16} {'field':<16} {'label':<8} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<12} {model.__name__:<16} {field:<16} {label:<8} {status}")

    # 2. ensure_exists: 存在/不存在 两种行为
    print("\n[2] ensure_exists 行为 (mock DB):")

    class _FakeDB:
        def __init__(self, found):
            self.found = found
        async def execute(self, stmt):
            class _R:
                def __init__(self, n): self.n = n
                def scalar(self):
                    return self.n
            return _R(self.found)

    async def demo_ensure_exists():
        try:
            await ensure_exists(_FakeDB(found=1), UserInfo, "user_id", "P001", entity_label="患者")
            print("  [OK]   user_id='P001' 存在 → 不抛异常")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")
        try:
            await ensure_exists(_FakeDB(found=0), UserInfo, "user_id", "P999", entity_label="患者")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [404]  user_id='P999' 不存在 → {e.detail}  (status={e.status_code})")

    asyncio.run(demo_ensure_exists())

    print("\n" + "=" * 60)
    print("总结: 患者存在 + source_id 类型匹配 + 单据归属 3 维度校验, 全用 HTTPException 兜底")
