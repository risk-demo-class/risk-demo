"""经销商风险画像 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import UserProfileResponse
from app.service.case import get_profile_tx

profile_router = APIRouter(prefix="/api/profile", tags=["画像"])


@profile_router.get("/{user_id}", response_model=UserProfileResponse)
async def api_get_profile(user_id: str, db: AsyncSession = Depends(get_db_async)):
    return await get_profile_tx(db, user_id)
