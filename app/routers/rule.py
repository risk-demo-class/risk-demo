"""Router 层：对齐源码的规则管理模块，当前先开放分页查询。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RiskRule
from app.routers.risk import get_session
from app.schemas import RuleListItem, RuleListResponse


rule_router = APIRouter(prefix="/api/rules", tags=["教育风控规则"])


@rule_router.get("", response_model=RuleListResponse)
def list_rules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> RuleListResponse:
    total = session.scalar(select(func.count()).select_from(RiskRule)) or 0
    rules = session.scalars(
        select(RiskRule).order_by(RiskRule.rule_id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return RuleListResponse(
        items=[RuleListItem.model_validate(rule, from_attributes=True) for rule in rules],
        total=total,
        page=page,
        page_size=page_size,
    )
