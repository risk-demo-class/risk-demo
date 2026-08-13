"""黑名单 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse
from app.service.case import add_blacklist, get_blacklist, remove_blacklist


blacklist_router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


@blacklist_router.get("", response_model=BlacklistListResponse)
async def api_list_blacklist(
    blacklist_type: str = Query(None, description="黑名单类型筛选: 用户/设备指纹/IP/银行卡号/身份证号"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db_async),
):
    total, items = await get_blacklist(
        db, page=page, page_size=page_size, blacklist_type=blacklist_type,
    )
    return BlacklistListResponse(
        items=items, total=total, page=page, page_size=page_size,
    )


@blacklist_router.post("", response_model=BlacklistResponse, status_code=201)
async def api_add_blacklist(
    data: BlacklistCreate,
    db: AsyncSession = Depends(get_db_async),
):
    try:
        result = await add_blacklist(db, data)
        # add_blacklist 内部 flush 拿 ID 但不 commit, 这里统一 commit
        await db.commit()
    except IntegrityError:
        # 【P1 修复 2026-08-12】并发下仍可能撞唯一索引, 转成可读的 409 而非裸 500
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"黑名单 {data.blacklist_type}={data.blacklist_value} 已存在",
        )
    return result


@blacklist_router.delete("/{blacklist_id}")
async def api_remove_blacklist(
    blacklist_id: int,
    db: AsyncSession = Depends(get_db_async),
):
    if not await remove_blacklist(db, blacklist_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"detail": "已移除"}
