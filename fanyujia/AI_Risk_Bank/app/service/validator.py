"""银行业务实体校验器。"""
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BankTransaction, LoanApplication, LoginLog, UserInfo
from app.schemas import RiskCheckRequest


async def ensure_exists(
    db: AsyncSession, model: type, field_name: str, value: Any, *, entity_label: str,
) -> None:
    if not value:
        raise HTTPException(status_code=400, detail=f"{entity_label}ID不能为空")
    stmt = select(func.count()).select_from(model).where(getattr(model, field_name) == value)
    if not (await db.execute(stmt)).scalar():
        raise HTTPException(status_code=404, detail=f"{entity_label}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="用户")


# 事件类型 → (业务模型, 主键字段, 展示名称)。银行版唯一的来源校验派发表。
_EVENT_SOURCE_VALIDATORS = {
    "信用卡交易": (BankTransaction, "txn_id", "交易"),
    "转账": (BankTransaction, "txn_id", "交易"),
    "贷款申请": (LoanApplication, "loan_id", "贷款申请"),
    "登录": (LoginLog, "login_id", "登录记录"),
}


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    model, field, label = _EVENT_SOURCE_VALIDATORS[request.event_type]
    await ensure_exists(db, model, field, request.source_id, entity_label=label)


async def _source_owner(db: AsyncSession, request: RiskCheckRequest) -> Optional[str]:
    model, field, _ = _EVENT_SOURCE_VALIDATORS[request.event_type]
    return (await db.execute(select(model.user_id).where(getattr(model, field) == request.source_id))).scalar_one_or_none()


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)
    owner = await _source_owner(db, request)
    if owner != request.user_id:
        raise HTTPException(status_code=403, detail="业务来源不属于请求用户")
