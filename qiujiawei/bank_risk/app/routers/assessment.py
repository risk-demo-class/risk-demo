"""评估历史 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.database import get_db_async
from bank_risk.app.models import RiskAssessment


assessment_router = APIRouter(prefix="/api/assessments", tags=["评估历史"])


@assessment_router.get("")
async def api_list_assessments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    """分页列出评估历史."""
    total = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
    )).scalar() or 0)
    stmt = (
        select(RiskAssessment)
        .order_by(RiskAssessment.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_assessment_to_dict(a) for a in items],
        "total": total, "page": page, "page_size": page_size,
    }


@assessment_router.get("/{assessment_id}")
async def api_get_assessment(
    assessment_id: str,
    db: AsyncSession = Depends(get_db_async),
):
    """评估详情."""
    assessment = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )).scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")
    return _assessment_to_dict(assessment)


def _assessment_to_dict(assessment: RiskAssessment) -> dict:
    """ORM → dict."""
    return {c.name: getattr(assessment, c.name) for c in assessment.__table__.columns}
