"""评估历史 API (列表 + 详情)"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_risk import TelecomRiskAssessment, TelecomRiskEvent
from app.schemas import (
    AssessmentDetailResponse, AssessmentItem, AssessmentListResponse, RuleHitInfo,
)

assessment_router = APIRouter(prefix="/api/assessments", tags=["评估历史"])


@assessment_router.get("", response_model=AssessmentListResponse)
async def list_assessments(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    msisdn: str | None = None,
    db: AsyncSession = Depends(get_db_async),
):
    """分页查询评估历史 (JOIN event 拿 event_type)."""
    stmt = select(
        TelecomRiskAssessment.assessment_id,
        TelecomRiskAssessment.event_id,
        TelecomRiskAssessment.msisdn,
        TelecomRiskEvent.event_type,
        TelecomRiskAssessment.final_score,
        TelecomRiskAssessment.risk_level,
        TelecomRiskAssessment.decision,
        TelecomRiskAssessment.rule_count,
        TelecomRiskAssessment.ml_score,
        TelecomRiskAssessment.ml_decision,
        TelecomRiskAssessment.create_time,
    ).select_from(TelecomRiskAssessment).join(
        TelecomRiskEvent, TelecomRiskAssessment.event_id == TelecomRiskEvent.event_id,
    )
    if msisdn:
        stmt = stmt.where(TelecomRiskAssessment.msisdn == msisdn)
    total = int((await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(TelecomRiskAssessment.create_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    items = [
        AssessmentItem(
            assessment_id=r.assessment_id, event_id=r.event_id, msisdn=r.msisdn,
            event_type=r.event_type, final_score=r.final_score, risk_level=r.risk_level,
            decision=r.decision, rule_count=r.rule_count,
            ml_score=float(r.ml_score) if r.ml_score is not None else None,
            ml_decision=r.ml_decision, create_time=r.create_time,
        ) for r in rows
    ]
    return AssessmentListResponse(items=items, total=total, page=page, page_size=page_size)


@assessment_router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
async def get_assessment(assessment_id: str, db: AsyncSession = Depends(get_db_async)):
    """评估详情 (含命中规则 + event_data)."""
    row = (await db.execute(
        select(
            TelecomRiskAssessment, TelecomRiskEvent.event_type,
            TelecomRiskEvent.event_source_id, TelecomRiskEvent.event_data,
        ).select_from(TelecomRiskAssessment)
        .join(TelecomRiskEvent, TelecomRiskAssessment.event_id == TelecomRiskEvent.event_id)
        .where(TelecomRiskAssessment.assessment_id == assessment_id)
    )).first()
    if not row:
        raise HTTPException(404, f"评估不存在: {assessment_id}")
    ast, event_type, event_source_id, event_data = row
    # 解析 rule_results JSON → RuleHitInfo 列表
    triggered = []
    if ast.rule_results:
        try:
            for h in json.loads(ast.rule_results):
                triggered.append(RuleHitInfo(**h))
        except (json.JSONDecodeError, TypeError):
            pass
    return AssessmentDetailResponse(
        assessment_id=ast.assessment_id, event_id=ast.event_id, msisdn=ast.msisdn,
        event_type=event_type, event_source_id=event_source_id,
        final_score=ast.final_score, risk_level=ast.risk_level, decision=ast.decision,
        rule_count=ast.rule_count, triggered_rules=triggered,
        ml_score=float(ast.ml_score) if ast.ml_score is not None else None,
        ml_decision=ast.ml_decision, create_time=ast.create_time,
        event_data=event_data,
    )
