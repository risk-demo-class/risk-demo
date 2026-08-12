"""仪表盘统计 API."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAssessment, RiskCase, RiskRule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@router.get("/stats")
async def api_dashboard_stats(
    db: AsyncSession = Depends(get_db_async),
) -> dict:
    """仪表盘汇总统计."""
    try:
        case_total = int(
            (await db.execute(select(func.count()).select_from(RiskCase))).scalar() or 0
        )
        assessment_total = int(
            (await db.execute(select(func.count()).select_from(RiskAssessment))).scalar() or 0
        )
        rule_total = int(
            (
                await db.execute(
                    select(func.count()).select_from(RiskRule).where(RiskRule.deleted_at.is_(None))
                )
            ).scalar()
            or 0
        )
        decision_rows = (
            await db.execute(
                select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)
            )
        ).all()
        return {
            "case_total": case_total,
            "assessment_total": assessment_total,
            "rule_total": rule_total,
            "decision_stats": {d: int(c) for d, c in decision_rows},
        }
    except Exception:
        logger.exception("仪表盘统计失败")
        raise
