"""案件管理 API (列表 + 详情 + 审核)"""
import json
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_risk import TelecomRiskAssessment, TelecomRiskCase
from app.schemas import (
    CaseDetailResponse, CaseItem, CaseListResponse, CaseReviewRequest,
    CaseStatistics, RuleHitInfo,
)

case_router = APIRouter(prefix="/api/cases", tags=["案件管理"])


@case_router.get("", response_model=CaseListResponse)
async def list_cases(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db_async),
):
    """分页查询案件."""
    stmt = select(
        TelecomRiskCase.case_id, TelecomRiskCase.assessment_id, TelecomRiskCase.msisdn,
        TelecomRiskCase.case_status, TelecomRiskCase.case_category,
        TelecomRiskAssessment.final_score, TelecomRiskAssessment.risk_level,
        TelecomRiskCase.create_time, TelecomRiskCase.source_id, TelecomRiskCase.event_type,
    ).select_from(TelecomRiskCase).outerjoin(
        TelecomRiskAssessment, TelecomRiskCase.assessment_id == TelecomRiskAssessment.assessment_id,
    )
    if status:
        stmt = stmt.where(TelecomRiskCase.case_status == status)
    total = int((await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(TelecomRiskCase.create_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    items = [
        CaseItem(
            case_id=r.case_id, assessment_id=r.assessment_id, msisdn=r.msisdn,
            case_status=r.case_status, case_category=r.case_category,
            final_score=r.final_score, risk_level=r.risk_level,
            create_time=r.create_time, source_id=r.source_id, event_type=r.event_type,
        ) for r in rows
    ]
    return CaseListResponse(items=items, total=total, page=page, page_size=page_size)


@case_router.get("/statistics", response_model=CaseStatistics)
async def case_statistics(db: AsyncSession = Depends(get_db_async)):
    """案件统计 (按状态 + 按类别)."""
    rows = (await db.execute(
        select(TelecomRiskCase.case_status, TelecomRiskCase.case_category, func.count())
        .group_by(TelecomRiskCase.case_status, TelecomRiskCase.case_category)
    )).all()
    stats = CaseStatistics()
    by_cat: dict[str, int] = {}
    for status, category, cnt in rows:
        cnt = int(cnt or 0)
        stats.total += cnt
        by_cat[category or "未知"] = by_cat.get(category or "未知", 0) + cnt
        if status == "待审核": stats.pending += cnt
        elif status == "审核中": stats.reviewing += cnt
        elif status == "已通过": stats.approved += cnt
        elif status == "已拒绝": stats.rejected += cnt
        elif status == "已关闭": stats.closed += cnt
        elif status == "已关停": stats.halted += cnt
    stats.by_category = by_cat
    return stats


@case_router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db_async)):
    """案件详情 (含命中规则 + 评估信息)."""
    row = (await db.execute(
        select(TelecomRiskCase, TelecomRiskAssessment.final_score,
               TelecomRiskAssessment.risk_level, TelecomRiskAssessment.decision,
               TelecomRiskAssessment.rule_results, TelecomRiskAssessment.ml_score,
               TelecomRiskAssessment.ml_decision)
        .select_from(TelecomRiskCase)
        .outerjoin(TelecomRiskAssessment, TelecomRiskCase.assessment_id == TelecomRiskAssessment.assessment_id)
        .where(TelecomRiskCase.case_id == case_id)
    )).first()
    if not row:
        raise HTTPException(404, f"案件不存在: {case_id}")
    case, final_score, risk_level, decision, rule_results, ml_score, ml_decision = row
    triggered = []
    if rule_results:
        try:
            for h in json.loads(rule_results):
                triggered.append(RuleHitInfo(**h))
        except (json.JSONDecodeError, TypeError):
            pass
    return CaseDetailResponse(
        case_id=case.case_id, assessment_id=case.assessment_id, msisdn=case.msisdn,
        case_status=case.case_status, case_category=case.case_category,
        risk_detail=case.risk_detail, reviewer=case.reviewer,
        review_comment=case.review_comment, review_time=case.review_time,
        create_time=case.create_time, final_score=final_score, risk_level=risk_level,
        decision=decision, triggered_rules=triggered,
        ml_score=float(ml_score) if ml_score is not None else None,
        ml_decision=ml_decision, source_id=case.source_id, event_type=case.event_type,
    )


@case_router.post("/{case_id}/review")
async def review_case(
    case_id: str, data: CaseReviewRequest, db: AsyncSession = Depends(get_db_async),
):
    """审核案件 (更新状态 + 审核人 + 意见)."""
    from datetime import datetime
    case = (await db.execute(
        select(TelecomRiskCase).where(TelecomRiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(404, f"案件不存在: {case_id}")
    case.case_status = data.decision
    case.reviewer = data.reviewer
    case.review_comment = data.review_comment
    case.review_time = datetime.now()
    await db.commit()
    return {"case_id": case_id, "case_status": data.decision, "reviewer": data.reviewer}
