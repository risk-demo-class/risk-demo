"""银行业务实体存在性、事件源匹配和水平越权校验。"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import BankCard, LoanApplication, LoginLog, Transaction, UserInfo
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
    """通用存在性校验，供用户等简单实体复用。"""
    field_label = field_label or f"{entity_label}ID"
    if value in (None, ""):
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    compare_value = cast_value(value) if cast_value else value
    statement = (
        select(func.count())
        .select_from(model)
        .where(getattr(model, field_name) == compare_value)
    )
    if not (await db.execute(statement)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(
            status_code=status_code, detail=f"{field_label}不存在: {value}"
        )


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


@dataclass(frozen=True)
class SourceValidatorSpec:
    model: type
    field_name: str
    owner_field_name: str | None
    label: str


_EVENT_SOURCE_VALIDATORS: dict[str, SourceValidatorSpec] = {
    "登录": SourceValidatorSpec(LoginLog, "login_id", "user_id", "登录记录"),
    "转账": SourceValidatorSpec(Transaction, "txn_id", None, "转账记录"),
    "贷款申请": SourceValidatorSpec(LoanApplication, "loan_id", "user_id", "贷款申请"),
    "绑卡": SourceValidatorSpec(BankCard, "card_id", "user_id", "银行卡"),
}


async def _ensure_owned_source(
    db: AsyncSession,
    request: RiskCheckRequest,
    spec: SourceValidatorSpec,
) -> None:
    """一次查询同时完成 source 存在性和用户归属校验。"""
    owner_column = getattr(spec.model, spec.owner_field_name)
    source_column = getattr(spec.model, spec.field_name)
    owner = (
        await db.execute(select(owner_column).where(source_column == request.source_id))
    ).scalar_one_or_none()
    if owner is None:
        raise HTTPException(
            status_code=400,
            detail=f"event_type={request.event_type} 与 source_id={request.source_id} 不匹配或记录不存在",
        )
    if owner != request.user_id:
        logger.warning(
            "水平越权拦截: event_type=%s source_id=%s owner=%s request_user=%s",
            request.event_type,
            request.source_id,
            owner,
            request.user_id,
        )
        raise HTTPException(status_code=403, detail=f"{spec.label}不属于请求用户")


async def _ensure_transfer_source(db: AsyncSession, request: RiskCheckRequest) -> None:
    """校验交易存在、付款卡归属，以及收付款卡关系有效。"""
    from_card = aliased(BankCard)
    to_card = aliased(BankCard)
    statement = (
        select(
            Transaction.from_card,
            Transaction.to_card,
            from_card.user_id.label("from_owner"),
            from_card.is_active.label("from_active"),
            to_card.is_active.label("to_active"),
        )
        .select_from(Transaction)
        .join(from_card, Transaction.from_card == from_card.card_id)
        .join(to_card, Transaction.to_card == to_card.card_id)
        .where(Transaction.txn_id == request.source_id)
    )
    row = (await db.execute(statement)).first()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail=f"event_type=转账 与 source_id={request.source_id} 不匹配或卡关系不存在",
        )
    if row.from_owner != request.user_id:
        logger.warning(
            "水平越权拦截: txn_id=%s from_owner=%s request_user=%s",
            request.source_id,
            row.from_owner,
            request.user_id,
        )
        raise HTTPException(status_code=403, detail="转账付款卡不属于请求用户")
    if row.from_card == row.to_card or not row.from_active or not row.to_active:
        raise HTTPException(status_code=400, detail="转账收付款卡关系无效")


async def ensure_source_matches_event_type(
    db: AsyncSession, request: RiskCheckRequest
) -> None:
    """按银行事件派发 source_id 类型和归属校验。"""
    spec = _EVENT_SOURCE_VALIDATORS.get(request.event_type)
    if spec is None:
        raise HTTPException(
            status_code=400, detail=f"不支持的银行事件类型: {request.event_type}"
        )
    if request.event_type == "转账":
        await _ensure_transfer_source(db, request)
        return
    await _ensure_owned_source(db, request, spec)


async def validate_risk_check_request(
    db: AsyncSession, request: RiskCheckRequest
) -> None:
    """process_event 第 1 步：用户存在，再校验事件源及归属。"""
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)


if __name__ == "__main__":
    print("银行事件 source_id 派发表")
    for event_type, spec in _EVENT_SOURCE_VALIDATORS.items():
        print(f"- {event_type}: {spec.model.__name__}.{spec.field_name}")
