"""告警 API: 列表 / 手动检查 / 处理"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAlert
from app.schemas import AlertItem, AlertListResponse, AlertResolveRequest
from app.service.alert import check_alerts


alert_router = APIRouter(prefix="/api/alerts", tags=["告警"])


def _to_item(a: RiskAlert) -> AlertItem:
    return AlertItem(
        alert_id=a.alert_id,
        alert_type=a.alert_type,
        alert_level=a.alert_level,
        alert_title=a.alert_title,
        alert_content=a.alert_content,
        metric_name=a.metric_name,
        metric_value=float(a.metric_value) if a.metric_value is not None else None,
        threshold=float(a.threshold) if a.threshold is not None else None,
        status=a.status,
        handler=a.handler,
        create_time=a.create_time,
    )


@alert_router.get("", response_model=AlertListResponse)
async def list_alerts(
    page: int = 1,
    page_size: int = 10,
    status: str = "",
    db: AsyncSession = Depends(get_db_async),
):
    stmt = select(RiskAlert)
    count_stmt = select(func.count()).select_from(RiskAlert)
    if status:
        stmt = stmt.where(RiskAlert.status == status)
        count_stmt = count_stmt.where(RiskAlert.status == status)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(RiskAlert.create_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return AlertListResponse(
        items=[_to_item(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@alert_router.post("/check")
async def manual_check(db: AsyncSession = Depends(get_db_async)):
    created = await check_alerts(db)
    return {"success": True, "created_count": len(created), "message": "告警检查完成"}


@alert_router.patch("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    body: AlertResolveRequest,
    db: AsyncSession = Depends(get_db_async),
):
    alert = (await db.execute(
        select(RiskAlert).where(RiskAlert.alert_id == alert_id)
    )).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail=f"告警不存在: {alert_id}")
    alert.status = body.status
    alert.handler = body.handler
    if body.status == "RESOLVED":
        alert.resolve_time = datetime.now()
    await db.commit()
    return {"success": True, "alert_id": alert_id, "status": alert.status}
