import hashlib
import hmac
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models_business import BlacklistExtra
from app.routers.common import blacklist_dict, page_meta
from app.schemas import BlacklistCreate
from app.service.action_log import record_action

router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])


def normalize_value(kind: str, raw: str) -> tuple[str, str]:
    clean = raw.strip().upper() if kind == "学号" else raw.strip()
    if kind not in ("身份证", "设备指纹"):
        return clean, clean
    key = os.getenv("RISK_HASH_KEY", "local-development-key").encode()
    digest = hmac.new(key, clean.encode(), hashlib.sha256).hexdigest()
    masked = f"{clean[:3]}***{clean[-4:]}" if len(clean) > 7 else "***"
    return digest, masked


@router.get("")
def list_blacklist(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    type: str | None = None, db: Session = Depends(get_session),
):
    conditions = [BlacklistExtra.deleted_at.is_(None)]
    if type:
        conditions.append(BlacklistExtra.type == type)
    total = db.scalar(select(func.count()).select_from(BlacklistExtra).where(*conditions)) or 0
    rows = list(db.scalars(select(BlacklistExtra).where(*conditions).order_by(desc(BlacklistExtra.created_at)).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [blacklist_dict(row) for row in rows], **page_meta(total, page, page_size)}


@router.post("", status_code=201)
def add_blacklist(data: BlacklistCreate, db: Session = Depends(get_session), operator: str = Header(default="admin", alias="X-Operator")):
    value, masked = normalize_value(data.type, data.value)
    row = db.scalar(select(BlacklistExtra).where(BlacklistExtra.type == data.type, BlacklistExtra.value == value))
    if row:
        before = {"status": row.status, "reason": row.reason, "deleted_at": row.deleted_at}
        row.status, row.deleted_at = "启用", None
        row.reason, row.expire_at, row.value_masked = data.reason, data.expire_at, masked
        after = {"status": row.status, "reason": row.reason}
    else:
        row = BlacklistExtra(type=data.type, value=value, value_masked=masked, reason=data.reason, status="启用", expire_at=data.expire_at, created_by=data.created_by)
        db.add(row)
        before, after = None, {"status": "启用", "reason": data.reason}
    record_action(
        db, operator=operator, action_type="ADD_BLACKLIST", target_type="blacklist",
        target_id=str(data.type) + ":" + masked, before_value=before, after_value=after,
    )
    db.commit()
    db.refresh(row)
    return blacklist_dict(row)


@router.delete("/{entry_id}")
def delete_blacklist(entry_id: int, db: Session = Depends(get_session), operator: str = Header(default="admin", alias="X-Operator")):
    row = db.get(BlacklistExtra, entry_id)
    if not row or row.deleted_at:
        raise HTTPException(404, "黑名单记录不存在")
    before = {"status": row.status}
    row.status, row.deleted_at = "停用", datetime.now()
    record_action(
        db, operator=operator, action_type="REMOVE_BLACKLIST", target_type="blacklist",
        target_id=str(entry_id), before_value=before, after_value={"status": "停用"},
    )
    db.commit()
    return {"ok": True}
