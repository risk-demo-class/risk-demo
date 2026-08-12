"""旅游业务查询和扩展黑名单 API。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.config import settings
from app.models import PassengerInfo, TravelBlacklistEntry, TravelOrder, VisaApplication
from app.security import require_admin
from app.service.action_log import record_action

travel_router = APIRouter(prefix="/api/travel", tags=["旅游业务"])


class TravelBlacklistCreate(BaseModel):
    entry_type: str
    entry_value_hash: str
    reason: str = ""
    expire_time: datetime | None = None


@travel_router.get("/orders")
async def list_orders(user_id: str | None = None, limit: int = Query(20, ge=1, le=100),
                      db: AsyncSession = Depends(get_db_async)):
    stmt = select(TravelOrder).order_by(TravelOrder.create_time.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(TravelOrder.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"order_id": r.order_id, "user_id": r.user_id, "order_type": r.order_type,
             "amount": float(r.total_amount), "dest_country": r.dest_country,
             "status": r.order_status, "create_time": r.create_time} for r in rows]


@travel_router.get("/passengers")
async def list_passengers(user_id: str, db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(select(PassengerInfo).where(
        PassengerInfo.user_id == user_id))).scalars().all()
    return [{"passenger_id": r.passenger_id, "name": r.name,
             "id_type": r.id_type, "nationality": r.nationality} for r in rows]


@travel_router.get("/visas")
async def list_visas(user_id: str, db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(select(VisaApplication).where(
        VisaApplication.user_id == user_id).order_by(
        VisaApplication.submit_time.desc()))).scalars().all()
    return [{"visa_id": r.visa_id, "country": r.dest_country,
             "visa_type": r.visa_type, "status": r.application_status,
             "submit_time": r.submit_time} for r in rows]


@travel_router.get("/identities/{identity_hash}/relations")
async def identity_relations(identity_hash: str, db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(select(PassengerInfo).where(
        PassengerInfo.id_number_hash == identity_hash))).scalars().all()
    if not rows:
        raise HTTPException(404, detail="未找到该证件关联")
    return {"identity_hash": identity_hash,
            "users": sorted({r.user_id for r in rows}),
            "passengers": [r.passenger_id for r in rows]}


@travel_router.get("/blacklist")
async def list_travel_blacklist(db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(select(TravelBlacklistEntry).where(
        TravelBlacklistEntry.deleted_at.is_(None)).order_by(
        TravelBlacklistEntry.create_time.desc()))).scalars().all()
    return [{"entry_id": r.entry_id, "entry_type": r.entry_type,
             "entry_value_hash": r.entry_value_hash, "reason": r.reason,
             "expire_time": r.expire_time} for r in rows]


@travel_router.post("/blacklist", status_code=201)
async def add_travel_blacklist(data: TravelBlacklistCreate,
                               db: AsyncSession = Depends(get_db_async),
                               _admin: str = Depends(require_admin)):
    if data.entry_type not in settings.TRAVEL_BLACKLIST_TYPES:
        raise HTTPException(400, detail=f"entry_type 必须是 {settings.TRAVEL_BLACKLIST_TYPES}")
    existing = (await db.execute(select(TravelBlacklistEntry).where(
        TravelBlacklistEntry.entry_type == data.entry_type,
        TravelBlacklistEntry.entry_value_hash == data.entry_value_hash,
    ))).scalar_one_or_none()
    if existing:
        existing.deleted_at = None
        existing.reason = data.reason
        existing.expire_time = data.expire_time
        row = existing
    else:
        row = TravelBlacklistEntry(**data.model_dump())
        db.add(row)
    await db.flush()
    await record_action(
        db, operator=_admin, action_type="ADD_BLACKLIST", target_type="blacklist",
        target_id=f"travel:{row.entry_id}", after_value=data.model_dump(mode="json"),
        remark=f"旅游扩展黑名单 {data.entry_type}",
    )
    await db.commit()
    return {"ok": True, "entry_type": row.entry_type,
            "entry_value_hash": row.entry_value_hash}


@travel_router.delete("/blacklist/{entry_id}")
async def remove_travel_blacklist(entry_id: int, db: AsyncSession = Depends(get_db_async),
                                  _admin: str = Depends(require_admin)):
    row = (await db.execute(select(TravelBlacklistEntry).where(
        TravelBlacklistEntry.entry_id == entry_id,
        TravelBlacklistEntry.deleted_at.is_(None)))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, detail="旅游黑名单记录不存在")
    await record_action(
        db, operator=_admin, action_type="REMOVE_BLACKLIST", target_type="blacklist",
        target_id=f"travel:{row.entry_id}",
        before_value={"entry_type": row.entry_type, "entry_value_hash": row.entry_value_hash},
        remark="移除旅游扩展黑名单",
    )
    row.deleted_at = datetime.now()
    await db.commit()
    return {"ok": True}
