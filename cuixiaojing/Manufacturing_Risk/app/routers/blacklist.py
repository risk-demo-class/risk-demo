"""黑名单管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse
from app.service.case import (
    add_blacklist,
    count_blacklists_tx,
    list_blacklists_tx,
    remove_blacklist_atomic,
)

blacklist_router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


@blacklist_router.get("", response_model=BlacklistListResponse)
async def api_list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    rows = await list_blacklists_tx(db, page=page, page_size=page_size)
    total = await count_blacklists_tx(db)
    return BlacklistListResponse(
        items=[BlacklistResponse(
            blacklist_id=b.blacklist_id,
            blacklist_type=b.blacklist_type,
            blacklist_value=b.blacklist_value,
            reason=b.reason,
            expire_time=b.expire_time,
            create_time=b.create_time,
        ) for b in rows],
        total=total, page=page, page_size=page_size,
    )


@blacklist_router.post("", response_model=BlacklistResponse, status_code=201)
async def api_add_blacklist(data: BlacklistCreate, db: AsyncSession = Depends(get_db_async)):
    return await add_blacklist(db, data)


@blacklist_router.delete("/{blacklist_id}")
async def api_remove_blacklist(blacklist_id: int, db: AsyncSession = Depends(get_db_async)):
    await remove_blacklist_atomic(db, blacklist_id)
    return {"detail": "已删除"}
