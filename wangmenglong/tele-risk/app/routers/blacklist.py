"""黑名单管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse
from app.service.blacklist import add_blacklist, get_blacklist, remove_blacklist

blacklist_router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


@blacklist_router.get("", response_model=BlacklistListResponse)
async def list_blacklist(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    return await get_blacklist(db, page=page, page_size=page_size)


@blacklist_router.post("", response_model=BlacklistResponse, status_code=201)
async def create_blacklist(data: BlacklistCreate, db: AsyncSession = Depends(get_db_async)):
    result = await add_blacklist(db, data)
    await db.commit()
    return result


@blacklist_router.delete("/{blacklist_id}")
async def delete_blacklist(blacklist_id: int, db: AsyncSession = Depends(get_db_async)):
    ok = await remove_blacklist(db, blacklist_id)
    if not ok:
        raise HTTPException(404, f"黑名单记录不存在: {blacklist_id}")
    await db.commit()
    return {"blacklist_id": blacklist_id, "deleted": True}
