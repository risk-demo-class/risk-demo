"""经销商风险画像 API（底层保留 user_id 兼容字段）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import UserProfileResponse
from app.service.case import get_user_profile


profile_router = APIRouter(prefix="/api/profile", tags=["经销商画像"])


@profile_router.get("/{user_id}", response_model=UserProfileResponse)
async def api_get_profile(user_id: str, db: AsyncSession = Depends(get_db_async)):
    profile = await get_user_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="经销商风险画像不存在")
    return profile
