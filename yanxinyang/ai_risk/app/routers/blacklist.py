# -*- coding: utf-8 -*-
"""L1 路由 · blacklist_router —— 黑名单（失信旅客名单）

对应教学宝典：
    * 第 16 章 `risk_blacklist` 表：5 种类型 / 过期时间 / 软删 / 命中计数
    * 第 4 章步骤 5：黑名单命中直接算「极高」规则，走一票否决

端点（3 个）：
    GET    /api/blacklist                     黑名单列表（类型/关键字/是否含失效）
    POST   /api/blacklist                     新增黑名单（幂等：同类型同值复活）
    DELETE /api/blacklist/{blacklist_id}      软删（解除拉黑）
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from app.database import Session, pool
from app.framework import HTTPError, Request, Router
from app.models import BLACKLIST_TYPES, RISK_LEVELS
from app.service.action_log import record_action

logger = logging.getLogger("ai_risk.routers.blacklist")

router = Router(prefix="/api/blacklist", tags=["黑名单"], name="blacklist_router")

_SOURCES = ("人工", "系统", "外部")


def _db() -> Session:
    return Session(pool.acquire())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ====================================================================== 1
@router.get("", "黑名单列表")
def list_blacklist(request: Request) -> Dict[str, Any]:
    blacklist_type = request.q("blacklist_type", "") or ""
    keyword = request.q("keyword", "") or ""
    include_disabled = request.q_bool("include_disabled", False)
    limit = min(max(request.q_int("limit", 50), 1), 500)
    offset = max(request.q_int("offset", 0), 0)

    where: List[str] = ["deleted_at IS NULL"]
    params: List[Any] = []
    if not include_disabled:
        where.append("is_enabled = 1")
    if blacklist_type:
        where.append("blacklist_type = ?")
        params.append(blacklist_type)
    if keyword:
        where.append("(blacklist_value LIKE ? OR reason LIKE ?)")
        params.extend([f"%{keyword}%"] * 2)
    clause = " AND ".join(where)

    db = _db()
    try:
        total = db.scalar(f"SELECT COUNT(*) FROM risk_blacklist WHERE {clause}", params)
        rows = db.fetch_all(
            f"""SELECT * FROM risk_blacklist WHERE {clause}
                ORDER BY create_time DESC, blacklist_id DESC LIMIT ? OFFSET ?""",
            params + [limit, offset])
        type_stats = {r["blacklist_type"]: r["cnt"] for r in db.fetch_all(
            "SELECT blacklist_type, COUNT(*) AS cnt FROM risk_blacklist "
            "WHERE deleted_at IS NULL AND is_enabled = 1 GROUP BY blacklist_type")}
        total_hit = db.scalar("SELECT COALESCE(SUM(hit_count),0) FROM risk_blacklist "
                              "WHERE deleted_at IS NULL")
    finally:
        db.close()

    now = _now()
    for row in rows:
        expire = row.get("expire_time")
        row["expired"] = bool(expire) and str(expire) < now
        row["permanent"] = not expire
    return {
        "success": True, "total": total, "items": rows, "limit": limit, "offset": offset,
        "type_stats": {t: type_stats.get(t, 0) for t in BLACKLIST_TYPES},
        "total_hit_count": total_hit,
        "meta": {"types": list(BLACKLIST_TYPES), "risk_levels": list(RISK_LEVELS),
                 "sources": list(_SOURCES)},
    }


# ====================================================================== 2
@router.post("", "新增黑名单")
def create_blacklist(request: Request) -> Dict[str, Any]:
    payload = request.json()
    blacklist_type = str(payload.get("blacklist_type") or "").strip()
    value = str(payload.get("blacklist_value") or "").strip()
    if blacklist_type not in BLACKLIST_TYPES:
        raise HTTPError(400, f"blacklist_type 必须是 {list(BLACKLIST_TYPES)} 之一")
    if not value:
        raise HTTPError(400, "blacklist_value 必填")
    risk_level = str(payload.get("risk_level") or "高")
    if risk_level not in RISK_LEVELS:
        raise HTTPError(400, f"risk_level 必须是 {list(RISK_LEVELS)} 之一")
    operator = str(payload.get("operator") or request.headers.get("x-operator", "") or "admin")

    values = {
        "blacklist_type": blacklist_type,
        "blacklist_value": value,
        "risk_level": risk_level,
        "reason": str(payload.get("reason") or "人工拉黑"),
        "source": str(payload.get("source") or "人工"),
        "operator": operator,
        "hit_count": 0,
        "expire_time": str(payload.get("expire_time") or "") or None,
        "is_enabled": 1,
        "create_time": _now(),
    }

    db = _db()
    try:
        # 类型 + 值唯一：已存在则复活并覆盖（幂等，避免脏重复）
        exists = db.fetch_one(
            "SELECT * FROM risk_blacklist WHERE blacklist_type = ? AND blacklist_value = ?"
            " ORDER BY blacklist_id DESC LIMIT 1", [blacklist_type, value])
        if exists and exists.get("deleted_at") is None and int(exists.get("is_enabled") or 0) == 1:
            raise HTTPError(400, f"该{blacklist_type}已在黑名单中: {value}")
        if exists:
            db.update("risk_blacklist",
                      {k: v for k, v in values.items()
                       if k not in ("blacklist_type", "blacklist_value")} | {"deleted_at": None},
                      "blacklist_id = ?", [exists["blacklist_id"]])
            new_id = exists["blacklist_id"]
        else:
            new_id = db.insert("risk_blacklist", values)
        record_action(db, operator=operator, action_type="新增黑名单", target_type="黑名单",
                      target_id=str(new_id), after_value=values,
                      remark=f"{blacklist_type}={value}")
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    finally:
        db.close()
    logger.info("新增黑名单 %s=%s by %s", blacklist_type, value, operator)
    return {"success": True, "data": values | {"blacklist_id": new_id}}


# ====================================================================== 3
@router.delete("/{blacklist_id}", "解除拉黑（软删）")
def delete_blacklist(request: Request) -> Dict[str, Any]:
    raw_id = request.path_params["blacklist_id"]
    try:
        blacklist_id = int(raw_id)
    except (TypeError, ValueError):
        raise HTTPError(400, f"blacklist_id 必须是整数: {raw_id}") from None
    operator = request.q("operator", "") or request.headers.get("x-operator", "") or "admin"

    db = _db()
    try:
        before = db.fetch_one(
            "SELECT * FROM risk_blacklist WHERE blacklist_id = ? AND deleted_at IS NULL",
            [blacklist_id])
        if not before:
            raise HTTPError(404, f"黑名单记录不存在或已解除: {blacklist_id}")
        db.update("risk_blacklist", {"deleted_at": _now(), "is_enabled": 0},
                  "blacklist_id = ?", [blacklist_id])
        record_action(db, operator=operator, action_type="解除黑名单", target_type="黑名单",
                      target_id=str(blacklist_id), before_value=before,
                      remark=f"{before['blacklist_type']}={before['blacklist_value']}")
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    finally:
        db.close()
    logger.info("解除黑名单 #%s by %s", blacklist_id, operator)
    return {"success": True, "message": f"已解除拉黑 #{blacklist_id}"}
