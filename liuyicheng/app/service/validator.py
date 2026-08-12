"""银行四场景业务校验：存在性、事件类型和客户归属。"""
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BankTransaction, LoanApplication, LoginLog, UserInfo
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)

_EVENT_MODELS = {
    "信用卡": (BankTransaction, BankTransaction.txn_id),
    "转账": (BankTransaction, BankTransaction.txn_id),
    "贷款": (LoanApplication, LoanApplication.loan_id),
    "登录": (LoginLog, LoginLog.login_id),
}


async def ensure_exists(
    db: AsyncSession,
    model: type,
    field_name: str,
    value: Any,
    *,
    entity_label: str,
    status_code: int = 404,
) -> None:
    if not value:
        raise HTTPException(status_code=400, detail=f"{entity_label}ID不能为空")
    count = (await db.execute(
        select(func.count()).select_from(model).where(getattr(model, field_name) == value)
    )).scalar() or 0
    if not count:
        raise HTTPException(status_code=status_code, detail=f"{entity_label}ID不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="客户")


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    """source_id 必须存在于事件对应的表，且记录属于请求客户。"""
    model, key = _EVENT_MODELS[request.event_type]
    row = (await db.execute(select(model).where(key == request.source_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"{request.event_type}业务ID不存在: {request.source_id}",
        )
    if row.user_id != request.user_id:
        logger.warning(
            "银行事件归属不一致: type=%s source=%s owner=%s request_user=%s",
            request.event_type, request.source_id, row.user_id, request.user_id,
        )
        raise HTTPException(status_code=403, detail="业务记录不属于该客户")
    if request.event_type in ("信用卡", "转账") and row.txn_type != request.event_type:
        raise HTTPException(
            status_code=400,
            detail=f"交易 {request.source_id} 的类型是 {row.txn_type}，不能按{request.event_type}检查",
        )


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
