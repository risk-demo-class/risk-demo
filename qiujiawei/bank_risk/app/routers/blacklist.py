"""黑名单管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.database import get_db_async
from bank_risk.app.models import RiskBlacklist


blacklist_router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


class BlacklistCreateRequest(BaseModel):
    """黑名单添加请求体"""
    blacklist_type: str
    blacklist_value: str
    reason: str = ""


@blacklist_router.get("")
async def api_list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    """分页列出黑名单."""
    total = int((await db.execute(
        select(func.count()).select_from(RiskBlacklist)
    )).scalar() or 0)
    stmt = (
        select(RiskBlacklist)
        .order_by(RiskBlacklist.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_blacklist_to_dict(b) for b in items],
        "total": total, "page": page, "page_size": page_size,
    }


@blacklist_router.post("", status_code=201)
async def api_add_blacklist(
    data: BlacklistCreateRequest,
    db: AsyncSession = Depends(get_db_async),
):
    """添加黑名单."""
    entry = RiskBlacklist(
        blacklist_type=data.blacklist_type,
        blacklist_value=data.blacklist_value,
        reason=data.reason,
    )
    db.add(entry)
    await db.commit()
    return _blacklist_to_dict(entry)


@blacklist_router.delete("/{entry_id}")
async def api_remove_blacklist(
    entry_id: int,
    db: AsyncSession = Depends(get_db_async),
):
    """删除黑名单记录."""
    entry = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.blacklist_id == entry_id)
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    await db.delete(entry)
    await db.commit()
    return {"detail": "已移除"}


def _blacklist_to_dict(entry: RiskBlacklist) -> dict:
    """ORM → dict."""
    return {c.name: getattr(entry, c.name) for c in entry.__table__.columns}
