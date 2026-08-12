"""用户画像 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskUserProfile


profile_router = APIRouter(prefix="/api/profile", tags=["用户画像"])


@profile_router.get("/{user_id}")
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db_async)):
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == user_id)
    )).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"用户画像不存在: {user_id}")
    return {
        "user_id": profile.user_id,
        "risk_score": profile.risk_score,
        "risk_level": profile.risk_level,
        "total_bookings": profile.total_bookings,
        "total_refunds": profile.total_refunds,
        "refund_rate": float(profile.refund_rate or 0),
        "avg_order_amount": float(profile.avg_order_amount or 0),
        "traveler_count": profile.traveler_count,
        "complaint_count": profile.complaint_count,
        "claim_count": profile.claim_count,
        "assessment_count": profile.assessment_count,
        "last_assessment_time": profile.last_assessment_time,
        "update_time": profile.update_time,
    }
