"""物流黑名单 API：核心三类 + 物流扩展四类。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import BlacklistExtra
from app.schemas import (
    BlacklistCreate,
    BlacklistExtraCreate,
    BlacklistExtraResponse,
    BlacklistListResponse,
    BlacklistResponse,
)
from app.service.case import add_blacklist, get_blacklist, remove_blacklist


blacklist_router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


def _extra_response(row: BlacklistExtra) -> BlacklistExtraResponse:
    return BlacklistExtraResponse(
        extra_id=row.extra_id,
        entity_type=row.entity_type,
        entity_value=row.entity_value,
        reason=row.reason,
        source=row.source,
        status=row.status,
        expire_time=row.expire_time,
        create_time=row.create_time,
    )


@blacklist_router.get("/extra", response_model=list[BlacklistExtraResponse])
async def api_list_extra_blacklist(db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(
        select(BlacklistExtra).where(BlacklistExtra.status == "启用")
        .order_by(BlacklistExtra.create_time.desc())
    )).scalars().all()
    return [_extra_response(row) for row in rows]


@blacklist_router.post("/extra", response_model=BlacklistExtraResponse, status_code=201)
async def api_add_extra_blacklist(
    data: BlacklistExtraCreate, db: AsyncSession = Depends(get_db_async),
):
    existing = (await db.execute(
        select(BlacklistExtra).where(
            BlacklistExtra.entity_type == data.entity_type,
            BlacklistExtra.entity_value == data.entity_value,
        )
    )).scalar_one_or_none()
    if existing:
        existing.reason = data.reason
        existing.expire_time = data.expire_time
        existing.status = "启用"
        row = existing
    else:
        row = BlacklistExtra(
            entity_type=data.entity_type,
            entity_value=data.entity_value,
            reason=data.reason,
            source="人工录入",
            expire_time=data.expire_time,
            create_time=datetime.now(),
        )
        db.add(row)
        await db.flush()
    await db.commit()
    return _extra_response(row)


@blacklist_router.delete("/extra/{extra_id}")
async def api_remove_extra_blacklist(
    extra_id: int, db: AsyncSession = Depends(get_db_async),
):
    row = (await db.execute(
        select(BlacklistExtra).where(BlacklistExtra.extra_id == extra_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="扩展黑名单记录不存在")
    row.status = "停用"
    await db.commit()
    return {"detail": "已停用"}


@blacklist_router.get("", response_model=BlacklistListResponse)
async def api_list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    total, items = await get_blacklist(db, page=page, page_size=page_size)
    return BlacklistListResponse(
        items=items, total=total, page=page, page_size=page_size,
    )


@blacklist_router.post("", response_model=BlacklistResponse, status_code=201)
async def api_add_blacklist(
    data: BlacklistCreate,
    db: AsyncSession = Depends(get_db_async),
):
    result = await add_blacklist(db, data)
    # add_blacklist 内部 flush 拿 ID 但不 commit, 这里统一 commit
    await db.commit()
    return result


@blacklist_router.delete("/{blacklist_id}")
async def api_remove_blacklist(
    blacklist_id: int,
    db: AsyncSession = Depends(get_db_async),
):
    if not await remove_blacklist(db, blacklist_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"detail": "已移除"}
