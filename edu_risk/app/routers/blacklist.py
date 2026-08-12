"""黑名单管理接口"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RiskBlacklist, UserInfo, gen_id

router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


class BlacklistAddRequest(BaseModel):
    user_id: str
    reason: str = "人工拉黑"
    source: str = "人工"   # 人工/AI/规则


@router.get("")
async def list_blacklist(status: str = "生效", db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.status == status,
                                    RiskBlacklist.is_deleted.is_(False))
        .order_by(RiskBlacklist.create_time.desc()))).scalars().all()
    return [{
        "blacklist_id": b.blacklist_id, "user_id": b.user_id, "reason": b.reason,
        "source": b.source, "status": b.status,
        "create_time": b.create_time.isoformat() if b.create_time else None,
    } for b in rows]


@router.post("")
async def add_blacklist(payload: BlacklistAddRequest, db: AsyncSession = Depends(get_db)):
    """加入黑名单。"""
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == payload.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, f"学员不存在: {payload.user_id}")
    row = RiskBlacklist(
        blacklist_id=gen_id("BL"),
        user_id=payload.user_id,
        reason=payload.reason,
        source=payload.source,
    )
    db.add(row)
    await db.commit()
    return {"blacklist_id": row.blacklist_id, "message": "已加入黑名单"}


@router.post("/{blacklist_id}/release")
async def release_blacklist(blacklist_id: str, db: AsyncSession = Depends(get_db)):
    """解除黑名单(软解除)。"""
    row = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.blacklist_id == blacklist_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"黑名单记录不存在: {blacklist_id}")
    row.status = "解除"
    await db.commit()
    return {"blacklist_id": blacklist_id, "status": "解除"}


@router.get("/check/{user_id}")
async def check_blacklist(user_id: str, db: AsyncSession = Depends(get_db)):
    """查询用户是否在黑名单。"""
    row = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.user_id == user_id,
                                    RiskBlacklist.status == "生效",
                                    RiskBlacklist.is_deleted.is_(False)))).scalar_one_or_none()
    return {"user_id": user_id, "in_blacklist": row is not None}
