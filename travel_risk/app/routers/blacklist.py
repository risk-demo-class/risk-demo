"""黑名单 API: 列表 / 添加 / 删除 (软删 + 审计)"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskBlacklist
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse
from app.service.action_log import record_action


blacklist_router = APIRouter(prefix="/api/blacklists", tags=["黑名单"])


def _to_response(b: RiskBlacklist) -> BlacklistResponse:
    return BlacklistResponse(
        blacklist_id=b.blacklist_id,
        blacklist_type=b.blacklist_type,
        blacklist_value=b.blacklist_value,
        reason=b.reason,
        expire_time=b.expire_time,
        create_time=b.create_time,
    )


@blacklist_router.get("", response_model=BlacklistListResponse)
async def list_blacklists(
    page: int = 1,
    page_size: int = 10,
    blacklist_type: str = "",
    db: AsyncSession = Depends(get_db_async),
):
    stmt = select(RiskBlacklist).where(RiskBlacklist.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(RiskBlacklist).where(RiskBlacklist.deleted_at.is_(None))
    if blacklist_type:
        stmt = stmt.where(RiskBlacklist.blacklist_type == blacklist_type)
        count_stmt = count_stmt.where(RiskBlacklist.blacklist_type == blacklist_type)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(RiskBlacklist.create_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return BlacklistListResponse(
        items=[_to_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@blacklist_router.post("", response_model=BlacklistResponse)
async def add_blacklist(body: BlacklistCreate, db: AsyncSession = Depends(get_db_async)):
    existing = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == body.blacklist_type,
            RiskBlacklist.blacklist_value == body.blacklist_value,
        )
    )).scalar_one_or_none()
    if existing:
        if existing.deleted_at is not None:
            # 软删过的条目: 恢复复用
            existing.deleted_at = None
            existing.reason = body.reason
            existing.expire_time = body.expire_time
            await record_action(
                db, "admin", "ADD_BLACKLIST", "blacklist", str(existing.blacklist_id),
                after_value=_to_response(existing).model_dump(mode="json"),
                remark=f"恢复黑名单 {body.blacklist_type}:{body.blacklist_value}",
            )
            await db.commit()
            await db.refresh(existing)
            return _to_response(existing)
        raise HTTPException(status_code=409, detail="该黑名单条目已存在")

    item = RiskBlacklist(
        blacklist_type=body.blacklist_type,
        blacklist_value=body.blacklist_value,
        reason=body.reason,
        expire_time=body.expire_time,
    )
    db.add(item)
    await db.flush()
    await record_action(
        db, "admin", "ADD_BLACKLIST", "blacklist", str(item.blacklist_id),
        after_value=_to_response(item).model_dump(mode="json"),
        remark=f"添加黑名单 {body.blacklist_type}:{body.blacklist_value}",
    )
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


@blacklist_router.delete("/{blacklist_id}")
async def remove_blacklist(blacklist_id: int, db: AsyncSession = Depends(get_db_async)):
    item = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_id == blacklist_id,
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"黑名单条目不存在: {blacklist_id}")
    before = _to_response(item).model_dump(mode="json")
    item.deleted_at = datetime.now()
    await record_action(
        db, "admin", "REMOVE_BLACKLIST", "blacklist", str(blacklist_id),
        before_value=before,
        after_value=None,
        remark=f"移除黑名单 {item.blacklist_type}:{item.blacklist_value}",
    )
    await db.commit()
    return {"success": True, "message": f"黑名单 {blacklist_id} 已移除"}
