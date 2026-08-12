from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.schemas import BlacklistCreate, BlacklistRemoveRequest
from models import RiskBlacklist


def normalize_value(value: str) -> str:
    return "".join(value.strip().upper().split())


def _is_effectively_active(row: RiskBlacklist, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return bool(row.is_active and (row.expires_at is None or row.expires_at > now))


def serialize_blacklist(row: RiskBlacklist) -> dict[str, Any]:
    return {
        "id": row.id,
        "blacklist_id": row.blacklist_id,
        "entity_type": row.entity_type,
        "entity_value": row.entity_value,
        "display_name": row.display_name,
        "reason_code": row.reason_code,
        "reason_detail": row.reason_detail,
        "severity": row.severity,
        "source": row.source,
        "source_refs": row.source_refs or [],
        "status": "ACTIVE" if _is_effectively_active(row) else ("REMOVED" if not row.is_active else "EXPIRED"),
        "effective_from": row.effective_from,
        "expires_at": row.expires_at,
        "hit_count": row.hit_count,
        "last_hit_at": row.last_hit_at,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "removed_at": row.removed_at,
        "removed_by": row.removed_by,
        "removed_reason": row.removed_reason,
    }


def list_blacklist(
    db: Session,
    page: int = 1,
    page_size: int = 50,
    entity_type: str | None = None,
    status: str = "ACTIVE",
    query: str | None = None,
) -> dict[str, Any]:
    now = datetime.now()
    conditions = []
    if entity_type:
        conditions.append(RiskBlacklist.entity_type == entity_type)
    if status == "ACTIVE":
        conditions.extend(
            [
                RiskBlacklist.is_active.is_(True),
                or_(RiskBlacklist.expires_at.is_(None), RiskBlacklist.expires_at > now),
            ]
        )
    elif status == "EXPIRED":
        conditions.extend([RiskBlacklist.is_active.is_(True), RiskBlacklist.expires_at <= now])
    elif status == "REMOVED":
        conditions.append(RiskBlacklist.is_active.is_(False))
    if query:
        term = f"%{query.strip()}%"
        conditions.append(
            or_(
                RiskBlacklist.entity_value.like(term),
                RiskBlacklist.display_name.like(term),
                RiskBlacklist.reason_code.like(term),
                RiskBlacklist.reason_detail.like(term),
            )
        )
    where = and_(*conditions) if conditions else True
    total = int(db.scalar(select(func.count()).select_from(RiskBlacklist).where(where)) or 0)
    rows = db.scalars(
        select(RiskBlacklist)
        .where(where)
        .order_by(RiskBlacklist.is_active.desc(), RiskBlacklist.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [serialize_blacklist(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def upsert_blacklist(db: Session, request: BlacklistCreate) -> dict[str, Any]:
    normalized = normalize_value(request.entity_value)
    row = db.scalar(
        select(RiskBlacklist).where(
            RiskBlacklist.entity_type == request.entity_type,
            RiskBlacklist.normalized_value == normalized,
        )
    )
    now = datetime.now()
    if row is None:
        row = RiskBlacklist(
            blacklist_id=f"BL-{uuid.uuid4().hex[:20]}",
            entity_type=request.entity_type,
            entity_value=request.entity_value.strip(),
            normalized_value=normalized,
            effective_from=now,
        )
        db.add(row)
    row.entity_value = request.entity_value.strip()
    row.display_name = request.display_name
    row.reason_code = request.reason_code.upper()
    row.reason_detail = request.reason_detail
    row.severity = request.severity
    row.source = request.source
    row.source_refs = request.source_refs
    row.expires_at = request.expires_at
    row.created_by = request.created_by
    row.is_active = True
    row.removed_at = None
    row.removed_by = None
    row.removed_reason = None
    db.commit()
    db.refresh(row)
    return serialize_blacklist(row)


def remove_blacklist(db: Session, blacklist_id: int, request: BlacklistRemoveRequest) -> bool:
    row = db.get(RiskBlacklist, blacklist_id)
    if row is None or not row.is_active:
        return False
    row.is_active = False
    row.removed_at = datetime.now()
    row.removed_by = request.removed_by.strip()
    row.removed_reason = request.removed_reason.strip()
    db.commit()
    return True


def check_blacklist_candidates(
    db: Session,
    candidates: Iterable[tuple[str, str | None, str | None]],
    record_hit: bool = False,
) -> list[dict[str, Any]]:
    normalized_candidates = [
        (entity_type, normalize_value(value), display_name)
        for entity_type, value, display_name in candidates
        if value
    ]
    if not normalized_candidates:
        return []
    now = datetime.now()
    clauses = [
        and_(RiskBlacklist.entity_type == entity_type, RiskBlacklist.normalized_value == value)
        for entity_type, value, _ in normalized_candidates
    ]
    rows = db.scalars(
        select(RiskBlacklist).where(
            RiskBlacklist.is_active.is_(True),
            or_(RiskBlacklist.expires_at.is_(None), RiskBlacklist.expires_at > now),
            or_(*clauses),
        )
    ).all()
    display_lookup = {(entity_type, value): display for entity_type, value, display in normalized_candidates}
    hits = []
    for row in rows:
        if record_hit:
            row.hit_count += 1
            row.last_hit_at = now
        item = serialize_blacklist(row)
        item["matched_display_name"] = display_lookup.get((row.entity_type, row.normalized_value))
        hits.append(item)
    if record_hit and rows:
        db.flush()
    return hits
