"""评估历史 API (全量评估, 含已结案)"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAssessment, RiskEvent, RiskFeature
from app.schemas import (
    AssessmentDetailResponse,
    AssessmentItem,
    AssessmentListResponse,
    RuleHitInfo,
)


assessment_router = APIRouter(prefix="/api/assessments", tags=["评估历史"])


def _to_item(a: RiskAssessment) -> AssessmentItem:
    return AssessmentItem(
        assessment_id=a.assessment_id,
        event_id=a.event_id,
        user_id=a.user_id,
        event_type=getattr(a, "event_type", "") or "",
        final_score=a.final_score,
        risk_level=a.risk_level,
        decision=a.decision,
        rule_count=a.rule_count,
        ml_score=float(a.ml_score) if a.ml_score is not None else None,
        ml_decision=a.ml_decision,
        create_time=a.create_time,
    )


@assessment_router.get("", response_model=AssessmentListResponse)
async def list_assessments(
    page: int = 1,
    page_size: int = 10,
    user_id: str = "",
    decision: str = "",
    db: AsyncSession = Depends(get_db_async),
):
    stmt = select(RiskAssessment)
    count_stmt = select(func.count()).select_from(RiskAssessment)
    if user_id:
        stmt = stmt.where(RiskAssessment.user_id == user_id)
        count_stmt = count_stmt.where(RiskAssessment.user_id == user_id)
    if decision:
        stmt = stmt.where(RiskAssessment.decision == decision)
        count_stmt = count_stmt.where(RiskAssessment.decision == decision)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(RiskAssessment.create_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    # 批量补事件类型 (risk_assessment 不存 event_type, 关联 risk_event)
    event_ids = [a.event_id for a in rows]
    event_type_map: dict[str, str] = {}
    if event_ids:
        event_rows = (await db.execute(
            select(RiskEvent.event_id, RiskEvent.event_type).where(RiskEvent.event_id.in_(event_ids))
        )).all()
        event_type_map = {eid: et for eid, et in event_rows}
    items = []
    for a in rows:
        item = _to_item(a)
        item.event_type = event_type_map.get(a.event_id, "")
        items.append(item)
    return AssessmentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@assessment_router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
async def get_assessment(assessment_id: str, db: AsyncSession = Depends(get_db_async)):
    a = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail=f"评估不存在: {assessment_id}")

    event = (await db.execute(
        select(RiskEvent.event_type, RiskEvent.event_source_id, RiskEvent.event_data)
        .where(RiskEvent.event_id == a.event_id)
    )).first()
    try:
        rules_raw = json.loads(a.rule_results) if a.rule_results else []
    except json.JSONDecodeError:
        rules_raw = []
    triggered_rules = [
        RuleHitInfo(**r) for r in rules_raw
        if isinstance(r, dict) and r.get("rule_id")
    ]

    feature_rows = (await db.execute(
        select(RiskFeature.feature_name, RiskFeature.feature_value)
        .where(RiskFeature.event_id == a.event_id)
    )).all()
    features = {
        name: float(value) if value is not None else 0.0
        for name, value in feature_rows
    }

    return AssessmentDetailResponse(
        assessment_id=a.assessment_id,
        event_id=a.event_id,
        user_id=a.user_id,
        event_type=event.event_type if event else "",
        event_source_id=event.event_source_id if event else "",
        final_score=a.final_score,
        risk_level=a.risk_level,
        decision=a.decision,
        rule_count=a.rule_count,
        triggered_rules=triggered_rules,
        ml_score=float(a.ml_score) if a.ml_score is not None else None,
        ml_decision=a.ml_decision,
        create_time=a.create_time,
        event_data=event.event_data if event else None,
        features=features,
    )
