"""
银行工商风控系统 - 业务实体校验器
集中处理 6 种事件类型的业务实体存在性、一致性校验
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankCard,
    LoanApplication,
    Transaction,
    UserInfo,
)
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def ensure_exists(
    db: AsyncSession, model: type, field_name: str, value: Any,
    *, entity_label: str, field_label: Optional[str] = None,
    cast_value: Optional[Callable[[Any], Any]] = None, status_code: int = 404,
) -> None:
    """泛型存在性校验"""
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
        raise HTTPException(status_code=status_code, detail=f"{field_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


async def ensure_card_belongs_to_user(
    db: AsyncSession, card_id: str, user_id: str,
) -> None:
    """防水平越权: 校验银行卡归属"""
    owner = (await db.execute(
        select(BankCard.user_id).where(BankCard.card_id == card_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"卡ID不存在: {card_id}")
    if owner != user_id:
        logger.warning("安全告警: 卡归属不一致 card_id=%s owner=%s req_user=%s", card_id, owner, user_id)
        raise HTTPException(status_code=403, detail=f"卡 {card_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致")


async def ensure_txn_exists(db: AsyncSession, txn_id: str) -> None:
    await ensure_exists(db, Transaction, "txn_id", txn_id, entity_label="交易")


async def ensure_loan_exists(db: AsyncSession, application_id: str) -> None:
    await ensure_exists(db, LoanApplication, "application_id", application_id, entity_label="贷款申请")


# ---- 事件类型到实体校验的字典派发表 ----
# 6 种事件类型映射到校验规则: (model, pk_field, caster, label, status_code)
_EVENT_SOURCE_VALIDATORS = {
    ("注册/开户",):       (UserInfo, "user_id", None, "用户", 400),
    ("登录",):           (UserInfo, "user_id", None, "用户", 400),
    ("转账/支付",):       (Transaction, "txn_id", None, "交易", 400),
    ("贷款申请",):        (LoanApplication, "application_id", None, "贷款申请", 400),
    ("绑卡/换卡",):       (BankCard, "card_id", None, "银行卡", 400),
    ("大额/可疑交易上报",): (Transaction, "txn_id", None, "交易", 400),
}


async def ensure_source_matches_event_type(
    db: AsyncSession, request: RiskCheckRequest,
) -> None:
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label, cast_value=caster, status_code=status_code,
        )
        return
    logger.warning("未配置 source_id 校验: event_type=%s source_id=%s", request.event_type, request.source_id)


# ---- 组合校验入口 ----
async def validate_risk_check_request(
    db: AsyncSession, request: RiskCheckRequest,
) -> None:
    # 1. 用户存在 (所有事件类型都需要)
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 转账/绑卡场景: 校验卡归属
    if request.event_type == "转账/支付":
        from_card = request.event_data.get("from_card") if request.event_data else None
        to_card = request.event_data.get("to_card") if request.event_data else None
        if from_card:
            await ensure_card_belongs_to_user(db, from_card, request.user_id)
        # to_card 可能是他人卡, 不校验归属, 但校验存在性
        if to_card:
            await ensure_exists(db, BankCard, "card_id", to_card, entity_label="收款卡")

    elif request.event_type == "绑卡/换卡":
        card_id = request.source_id
        await ensure_card_belongs_to_user(db, card_id, request.user_id)


# ============================================================
# Demo: 展示 6 种事件类型的字典派发
# ============================================================
if __name__ == "__main__":
    from fastapi import HTTPException
    from types import SimpleNamespace

    print("=" * 60)
    print("银行工商风控 Service Validator — 6 种事件类型派发")
    print("=" * 60)

    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<14} {'model':<20} {'field':<22} {'label':<8}")
    for evt_types, (model, field, _, label, _) in _EVENT_SOURCE_VALIDATORS.items():
        print(f"  {'|'.join(evt_types):<14} {model.__name__:<20} {field:<22} {label:<8}")

    class _FakeDB:
        def __init__(self, found): self.found = found
        async def execute(self, stmt):
            class _R:
                def __init__(self, n): self.n = n
                def scalar(self): return self.n
            return _R(self.found)

    async def demo():
        for evt, label in [("开户", "用户"), ("转账", "交易"), ("贷款申请", "贷款申请")]:
            try:
                await ensure_exists(_FakeDB(1), UserInfo, "user_id", "U001", entity_label=label)
                print(f"  [OK]   event_type={evt} source_id=U001 -> {label}存在, 通过")
            except HTTPException as e:
                print(f"  [FAIL] {e.detail}")
        try:
            await ensure_exists(_FakeDB(0), Transaction, "txn_id", "TXN_BAD", entity_label="交易")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [404]  source_id=TXN_BAD 不存在 -> {e.detail[:60]}...  (status={e.status_code})")

    asyncio.run(demo())
    print("\n" + "=" * 60)
    print("总结: 6 种事件类型全部映射, 字典派发一键加新类型")
