# -*- coding: utf-8 -*-
"""L1 路由 · profile_router —— 用户风险画像（旅客常飞档案）

对应教学宝典第 16 章 `risk_user_profile`（1:1 user_info），由 7 步流水线
步骤 7 的 `_update_user_profile` 增量维护：
    total_events / risk_event_count / 四种决策计数 / case_count / blacklist_hit_count
    last_* 快照 + max/avg 融合分 + profile_level

端点（2 个）：
    GET    /api/profiles              画像列表（按风险倒排）
    GET    /api/profiles/{user_id}    画像详情（业务总览 + 事件时间线 + 案件 + 撞黑）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.database import Session, pool
from app.framework import HTTPError, Request, Router
from app.models import RISK_LEVELS

logger = logging.getLogger("ai_risk.routers.profile")

router = Router(prefix="/api/profiles", tags=["用户画像"], name="profile_router")


def _db() -> Session:
    return Session(pool.acquire())


# ====================================================================== 1
@router.get("", "用户风险画像列表")
def list_profiles(request: Request) -> Dict[str, Any]:
    keyword = request.q("keyword", "") or ""
    level = request.q("profile_level", "") or ""
    min_score = request.q_int("min_score", 0)
    limit = min(max(request.q_int("limit", 20), 1), 200)
    offset = max(request.q_int("offset", 0), 0)
    order = request.q("order_by", "max_final_score") or "max_final_score"
    if order not in ("max_final_score", "avg_final_score", "total_events",
                     "risk_event_count", "last_event_time", "reject_count"):
        order = "max_final_score"

    where: List[str] = ["1=1"]
    params: List[Any] = []
    if level:
        where.append("p.profile_level = ?")
        params.append(level)
    if min_score:
        where.append("p.max_final_score >= ?")
        params.append(min_score)
    if keyword:
        where.append("(p.user_id LIKE ? OR u.user_name LIKE ? OR u.phone LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    clause = " AND ".join(where)

    db = _db()
    try:
        total = db.scalar(
            f"""SELECT COUNT(*) FROM risk_user_profile p
                LEFT JOIN user_info u ON u.user_id = p.user_id WHERE {clause}""", params)
        rows = db.fetch_all(
            f"""SELECT p.*, u.user_name, u.phone, u.user_level, u.register_time
                FROM risk_user_profile p
                LEFT JOIN user_info u ON u.user_id = p.user_id
                WHERE {clause}
                ORDER BY p.{order} DESC, p.total_events DESC LIMIT ? OFFSET ?""",
            params + [limit, offset])
        level_stats = {r["profile_level"]: r["cnt"] for r in db.fetch_all(
            "SELECT profile_level, COUNT(*) AS cnt FROM risk_user_profile GROUP BY profile_level")}
    finally:
        db.close()

    return {"success": True, "total": total, "items": rows, "limit": limit, "offset": offset,
            "level_stats": {lv: level_stats.get(lv, 0) for lv in RISK_LEVELS},
            "meta": {"levels": list(RISK_LEVELS), "order_by": order}}


# ====================================================================== 2
@router.get("/{user_id}", "画像详情（业务总览 + 事件时间线）")
def profile_detail(request: Request) -> Dict[str, Any]:
    user_id = request.path_params["user_id"]
    db = _db()
    try:
        user = db.fetch_one("SELECT * FROM user_info WHERE user_id = ?", [user_id])
        if not user:
            raise HTTPError(404, f"用户不存在: {user_id}")
        profile = db.fetch_one("SELECT * FROM risk_user_profile WHERE user_id = ?", [user_id])

        # ---- 业务总览（宝典 8 维订单特征的原始来源）----
        business = {
            "order_count": db.scalar("SELECT COUNT(*) FROM order_info WHERE user_id = ?", [user_id]),
            "order_amount": round(float(db.scalar(
                "SELECT COALESCE(SUM(total_amount),0) FROM order_info WHERE user_id = ?", [user_id])), 2),
            "refund_count": db.scalar(
                "SELECT COUNT(*) FROM refund_record r JOIN order_info o ON o.order_id = r.order_id "
                "WHERE o.user_id = ?", [user_id]),
            "postsale_count": db.scalar("SELECT COUNT(*) FROM postsale WHERE user_id = ?", [user_id]),
            "complaint_count": db.scalar(
                "SELECT COUNT(*) FROM complaint_record WHERE user_id = ?", [user_id]),
            "cancel_count": db.scalar(
                "SELECT COUNT(*) FROM cancel_record c JOIN order_info o ON o.order_id = c.order_id "
                "WHERE o.user_id = ?", [user_id]),
            "address_count": db.scalar(
                "SELECT COUNT(*) FROM user_address WHERE user_id = ?", [user_id]),
            "device_count": db.scalar("SELECT COUNT(*) FROM device_info WHERE user_id = ?", [user_id]),
            "login_count": db.scalar("SELECT COUNT(*) FROM login_log WHERE user_id = ?", [user_id]),
        }

        events = db.fetch_all(
            """SELECT e.event_id, e.event_type, e.source_id, e.event_time, e.client_ip,
                      a.assessment_id, a.rule_score, a.ml_score, a.final_score,
                      a.risk_level, a.decision, a.hit_rule_count, a.is_veto, a.reason
               FROM risk_event e
               LEFT JOIN risk_assessment a ON a.event_id = e.event_id
               WHERE e.user_id = ? ORDER BY e.event_time DESC, e.event_id DESC LIMIT 50""",
            [user_id])
        cases = db.fetch_all(
            "SELECT case_id, case_status, risk_level, final_score, reviewer, review_comment, "
            "create_time FROM risk_case WHERE user_id = ? AND deleted_at IS NULL "
            "ORDER BY create_time DESC LIMIT 20", [user_id])
        addresses = db.fetch_all(
            "SELECT * FROM user_address WHERE user_id = ? ORDER BY create_time DESC", [user_id])
        blacklist = db.fetch_all(
            """SELECT * FROM risk_blacklist WHERE deleted_at IS NULL AND is_enabled = 1
               AND ((blacklist_type = '用户' AND blacklist_value = ?)
                 OR (blacklist_type = '手机号' AND blacklist_value = ?))""",
            [user_id, user.get("phone") or ""])
        decision_hist = {r["decision"]: r["cnt"] for r in db.fetch_all(
            "SELECT decision, COUNT(*) AS cnt FROM risk_assessment WHERE user_id = ? "
            "GROUP BY decision", [user_id])}
    finally:
        db.close()

    return {"success": True, "data": {
        "user": user,
        "profile": profile or {"user_id": user_id, "total_events": 0,
                               "profile_level": "低", "note": "该用户尚无风控事件"},
        "business": business,
        "events": events,
        "cases": cases,
        "addresses": addresses,
        "blacklist": blacklist,
        "decision_histogram": decision_hist,
    }}
