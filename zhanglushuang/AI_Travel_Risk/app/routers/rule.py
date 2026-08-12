"""规则管理 API."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskRule
from app.schemas import RuleCreate, RuleListResponse, RuleResponse, RuleUpdate
from app.service.action_log import record_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rules", tags=["规则"])


def _to_response(rule: RiskRule) -> RuleResponse:
    return RuleResponse(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        rule_category=rule.rule_category,
        event_type=rule.event_type,
        rule_condition=rule.rule_condition,
        risk_level=rule.risk_level,
        risk_score=rule.risk_score,
        action=rule.action,
        is_enabled=rule.is_enabled,
        priority=rule.priority,
        description=rule.description,
        create_time=rule.create_time,
        update_time=rule.update_time,
    )


@router.get("", response_model=RuleListResponse)
async def api_list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_async),
) -> RuleListResponse:
    """规则列表."""
    filters = [RiskRule.deleted_at.is_(None)]
    if event_type:
        filters.append(RiskRule.event_type.in_([event_type, "通用"]))
    total = int(
        (await db.execute(select(func.count()).select_from(RiskRule).where(*filters))).scalar()
        or 0
    )
    rows = list(
        (
            await db.execute(
                select(RiskRule)
                .where(*filters)
                .order_by(RiskRule.priority.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return RuleListResponse(
        items=[_to_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=RuleResponse, status_code=201)
async def api_create_rule(
    data: RuleCreate,
    db: AsyncSession = Depends(get_db_async),
) -> RuleResponse:
    """新增规则."""
    try:
        row = RiskRule(
            rule_id=data.rule_id,
            rule_name=data.rule_name,
            rule_category=data.rule_category,
            event_type=data.event_type,
            rule_condition=data.rule_condition,
            risk_level=data.risk_level,
            risk_score=data.risk_score,
            action=data.action,
            priority=data.priority,
            description=data.description,
        )
        db.add(row)
        await db.flush()
        await record_action(
            db,
            operator="admin",
            action_type="CREATE_RULE",
            target_type="rule",
            target_id=data.rule_id,
            after_value=data.model_dump(),
        )
        await db.commit()
        return _to_response(row)
    except Exception:
        logger.exception("新增规则失败")
        await db.rollback()
        raise


@router.put("/{rule_id}", response_model=RuleResponse)
async def api_update_rule(
    rule_id: str,
    data: RuleUpdate,
    db: AsyncSession = Depends(get_db_async),
) -> RuleResponse:
    """更新规则."""
    row = (
        await db.execute(
            select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None)).limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    try:
        before = row.condition_dict
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.update_time = datetime.now()
        await record_action(
            db,
            operator="admin",
            action_type="UPDATE_RULE",
            target_type="rule",
            target_id=rule_id,
            before_value={"rule_condition": before},
            after_value={"rule_condition": row.rule_condition},
        )
        await db.commit()
        return _to_response(row)
    except Exception:
        logger.exception("更新规则失败: %s", rule_id)
        await db.rollback()
        raise


@router.delete("/{rule_id}")
async def api_delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_async),
) -> dict:
    """软删除规则."""
    row = (
        await db.execute(
            select(RiskRule).where(RiskRule.rule_id == rule_id, RiskRule.deleted_at.is_(None)).limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    try:
        before = row.condition_dict
        row.deleted_at = datetime.now()
        await record_action(
            db,
            operator="admin",
            action_type="DELETE_RULE",
            target_type="rule",
            target_id=rule_id,
            before_value={"rule_condition": before},
        )
        await db.commit()
        return {"detail": "已删除"}
    except Exception:
        logger.exception("删除规则失败: %s", rule_id)
        await db.rollback()
        raise
