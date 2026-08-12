"""告警管理 API"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.database import get_db_async
from bank_risk.app.models import RiskAlert


alert_router = APIRouter(prefix="/api/alerts", tags=["告警"])


# 注意路由顺序: "/unresolved-count" 必须在 "/{alert_id}" 之前注册
@alert_router.get("")
async def api_list_alerts(
    status: str = Query(None, description="状态过滤: PENDING/HANDLING/RESOLVED/IGNORED"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    """分页列出告警 (支持 status 筛选)."""
    count_stmt = select(func.count()).select_from(RiskAlert)
    if status:
        count_stmt = count_stmt.where(RiskAlert.status == status)
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = select(RiskAlert).order_by(RiskAlert.create_time.desc())
    if status:
        stmt = stmt.where(RiskAlert.status == status)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_alert_to_dict(a) for a in items],
        "total": total, "page": page, "page_size": page_size,
    }


@alert_router.get("/unresolved-count")
async def api_unresolved_count(db: AsyncSession = Depends(get_db_async)):
    """未处理告警数."""
    count = int((await db.execute(
        select(func.count()).select_from(RiskAlert)
        .where(RiskAlert.status != "RESOLVED")
    )).scalar() or 0)
    return {"unresolved_count": count}


@alert_router.patch("/{alert_id}/resolve")
async def api_resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db_async),
):
    """标记告警已处理."""
    alert = (await db.execute(
        select(RiskAlert).where(RiskAlert.alert_id == alert_id)
    )).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    alert.status = "RESOLVED"
    alert.resolve_time = datetime.now()
    await db.commit()
    return {"alert_id": alert_id, "status": "RESOLVED"}


def _alert_to_dict(alert: RiskAlert) -> dict:
    """ORM → dict."""
    return {c.name: getattr(alert, c.name) for c in alert.__table__.columns}
