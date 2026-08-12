"""银行版业务实体校验。"""
from typing import Any, Callable, Optional
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import BankUserInfo, BankTransaction, LoanApplication, LoginLog
from app.schemas import RiskCheckRequest


async def ensure_exists(db: AsyncSession, model: type, field_name: str, value: Any, *, entity_label: str, field_label: Optional[str] = None, cast_value: Optional[Callable[[Any], Any]] = None, status_code: int = 404) -> None:
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_label or entity_label + 'ID'}不能为空")
    compare_value = cast_value(value) if cast_value else value
    stmt = select(func.count()).select_from(model).where(getattr(model, field_name) == compare_value)
    if not (await db.execute(stmt)).scalar():
        raise HTTPException(status_code=status_code, detail=f"{field_label or entity_label + 'ID'}不存在: {value}")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, BankUserInfo, "user_id", user_id, entity_label="客户")


_EVENT_SOURCE_VALIDATORS = {
    "信用卡申请": (BankUserInfo, "user_id", None, "信用卡申请客户"),
    "贷款申请": (LoanApplication, "loan_id", None, "贷款申请"),
    "大额转账": (BankTransaction, "txn_id", None, "交易流水"),
    "异常登录": (LoginLog, "login_id", None, "登录记录"),
}


async def ensure_source_matches_event_type(db: AsyncSession, request: RiskCheckRequest) -> None:
    config = _EVENT_SOURCE_VALIDATORS.get(request.event_type)
    if not config:
        raise HTTPException(status_code=400, detail=f"不支持的银行事件类型: {request.event_type}")
    model, field, caster, label = config
    await ensure_exists(db, model, field, request.source_id, entity_label=label, cast_value=caster, status_code=404)
    if request.event_type == "信用卡申请":
        return
    owner = (await db.execute(select(model.user_id).where(getattr(model, field) == request.source_id))).scalar_one_or_none()
    if owner and owner != request.user_id:
        raise HTTPException(status_code=403, detail=f"{label} {request.source_id} 属于客户 {owner}, 与请求客户不一致")


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    await ensure_user_exists(db, request.user_id)
    await ensure_source_matches_event_type(db, request)


if __name__ == "__main__":
    print("银行版校验事件:", ", ".join(_EVENT_SOURCE_VALIDATORS))
