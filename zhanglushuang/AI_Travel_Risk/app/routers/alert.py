"""告警 API."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAlert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["告警"])


@router.get("")
async def api_list_alerts(
    db: AsyncSession = Depends(get_db_async),
) -> dict:
    """告警列表."""
    try:
        rows = list((await db.execute(select(RiskAlert).order_by(RiskAlert.create_time.desc()).limit(50))).scalars().all())
        return {
            "items": [
                {
                    "alert_id": r.alert_id,
                    "alert_type": r.alert_type,
                    "alert_level": r.alert_level,
                    "alert_title": r.alert_title,
                    "status": r.status,
                    "create_time": r.create_time,
                }
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception:
        logger.exception("告警列表查询失败")
        raise
