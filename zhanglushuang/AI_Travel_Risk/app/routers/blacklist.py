"""黑名单管理 API."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse
from app.service.case import add_blacklist, get_blacklist, remove_blacklist

router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


@router.get("", response_model=BlacklistListResponse)
async def api_list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    blacklist_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_async),
) -> BlacklistListResponse:
    total, items = await get_blacklist(
        db,
        page=page,
        page_size=page_size,
        blacklist_type=blacklist_type,
    )
    return BlacklistListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=BlacklistResponse, status_code=201)
async def api_add_blacklist(
    data: BlacklistCreate,
    db: AsyncSession = Depends(get_db_async),
) -> BlacklistResponse:
    result = await add_blacklist(db, data)
    await db.commit()
    return result


@router.delete("/{blacklist_id}")
async def api_remove_blacklist(
    blacklist_id: int,
    db: AsyncSession = Depends(get_db_async),
) -> dict:
    if not await remove_blacklist(db, blacklist_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    await db.commit()
    return {"detail": "已移除"}
