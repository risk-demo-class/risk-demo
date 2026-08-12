"""学员风险画像接口"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RiskBlacklist, RiskUserProfile, UserInfo

router = APIRouter(prefix="/api/users", tags=["学员画像"])


@router.get("/{user_id}/profile")
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    """查询学员风险画像 + 黑名单状态。"""
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, f"学员不存在: {user_id}")
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == user_id))).scalar_one_or_none()
    black = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.user_id == user_id,
                                    RiskBlacklist.status == "生效",
                                    RiskBlacklist.is_deleted.is_(False)))).scalar_one_or_none()
    return {
        "user_id": user.user_id,
        "user_name": user.user_name,
        "user_level": user.user_level,
        "register_time": user.register_time.isoformat() if user.register_time else None,
        "profile": {
            "total_checks": profile.total_checks if profile else 0,
            "total_cases": profile.total_cases if profile else 0,
            "max_score": float(profile.max_score) if profile else 0,
            "avg_score": float(profile.avg_score) if profile else 0,
            "risk_tag": profile.risk_tag if profile else "正常",
        },
        "in_blacklist": black is not None,
        "blacklist_reason": black.reason if black else None,
    }
