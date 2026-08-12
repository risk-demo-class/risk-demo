"""客户风险画像 API。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import UserProfileResponse
from app.service.admin import user_profile


router = APIRouter(prefix="/api/profile", tags=["客户画像"])


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db_async),
) -> UserProfileResponse:
    result = await user_profile(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="客户画像不存在，请先执行一次风险检查")
    return result
