"""风控事件查询接口"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RiskEvent

router = APIRouter(prefix="/api/events", tags=["风控事件"])


@router.get("")
async def list_events(page: int = 1, page_size: int = 20,
                      event_type: str | None = None, user_id: str | None = None,
                      db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    conds = []
    if event_type:
        conds.append(RiskEvent.event_type == event_type)
    if user_id:
        conds.append(RiskEvent.user_id == user_id)
    # 真实总数(count),供前端分页
    total = (await db.execute(
        select(func.count()).select_from(RiskEvent).where(*conds))).scalar() or 0
    stmt = (select(RiskEvent).where(*conds)
            .order_by(RiskEvent.create_time.desc())
            .offset((page - 1) * page_size).limit(page_size))
    events = (await db.execute(stmt)).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{
            "event_id": e.event_id, "event_type": e.event_type, "user_id": e.user_id,
            "source_id": e.source_id,
            "create_time": e.create_time.isoformat() if e.create_time else None,
        } for e in events],
    }
