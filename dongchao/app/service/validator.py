"""
银行风控系统 - 业务实体校验器
集中处理"用户/交易/贷款/登录"等业务实体的存在性、一致性校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    LoanApplication,
    LoginLog,
    Transaction,
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
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


async def ensure_card_belongs_to_user(
    db: AsyncSession,
    card_id: str,
    user_id: str,
) -> None:
    """防水平越权: 卡必须属于请求用户"""
    from app.models import BankCard
    owner = (await db.execute(
        select(BankCard.user_id).where(BankCard.card_id == card_id).limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"银行卡ID不存在: {card_id}")
    if owner != user_id:
        logger.warning("安全告警: 银行卡归属不一致 card_id=%s, owner=%s, request_user=%s",
                       card_id, owner, user_id)
        raise HTTPException(
            status_code=403,
            detail=f"银行卡 {card_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


async def ensure_transaction_belongs_to_user(
    db: AsyncSession,
    txn_id: str,
    user_id: str,
) -> None:
    """交易归属校验: Transaction.from_card → BankCard.user_id == user_id"""
    from app.models import BankCard
    owner = (await db.execute(
        select(BankCard.user_id)
        .select_from(Transaction)
        .join(BankCard, Transaction.from_card == BankCard.card_id)
        .where(Transaction.txn_id == txn_id)
        .limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"交易ID不存在: {txn_id}")
    if owner != user_id:
        logger.warning("安全告警: 交易归属不一致 txn_id=%s, owner=%s, request_user=%s",
                       txn_id, owner, user_id)
        raise HTTPException(
            status_code=403,
            detail=f"交易 {txn_id} 不属于用户 {user_id}",
        )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
_EVENT_SOURCE_VALIDATORS = {
    ("转账",): (Transaction, "txn_id", None, "交易", 400),
    ("贷款申请",): (LoanApplication, "loan_id", None, "贷款申请", 400),
    ("登录",): (LoginLog, "login_id", None, "登录记录", 400),
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

    # 3. 转账场景: 校验交易归属 (防绕过)
    if request.event_type == "转账":
        await ensure_transaction_belongs_to_user(db, request.source_id, request.user_id)