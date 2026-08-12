"""用户风险画像 API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import UserProfileResponse
from app.service.case import get_user_profile

router = APIRouter(prefix="/api/profile", tags=["画像"])


@router.get("/{user_id}", response_model=UserProfileResponse)
async def api_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db_async),
) -> UserProfileResponse:
    return await get_user_profile(db, user_id)
