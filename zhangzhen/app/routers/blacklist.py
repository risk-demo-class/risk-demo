"""八类银行黑名单管理 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_risk import BlacklistType
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse
from app.service.admin import add_blacklist, list_blacklist, remove_blacklist


router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


@router.get("", response_model=BlacklistListResponse)
async def get_blacklist(
    blacklist_type: BlacklistType | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
) -> BlacklistListResponse:
    return await list_blacklist(
        db, blacklist_type=blacklist_type, page=page, page_size=page_size
    )


@router.post("", response_model=BlacklistResponse, status_code=201)
async def post_blacklist(
    data: BlacklistCreate,
    db: AsyncSession = Depends(get_db_async),
) -> BlacklistResponse:
    async with db.begin():
        return await add_blacklist(db, data)


@router.delete("/{blacklist_id}")
async def delete_blacklist(
    blacklist_id: int,
    operator: str = Query(default="admin", min_length=1, max_length=50),
    db: AsyncSession = Depends(get_db_async),
) -> dict[str, str]:
    async with db.begin():
        removed = await remove_blacklist(db, blacklist_id, operator=operator)
        if not removed:
            raise HTTPException(status_code=404, detail="黑名单记录不存在")
    return {"detail": "黑名单已软删除"}
