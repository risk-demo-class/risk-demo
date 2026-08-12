# -*- coding: utf-8 -*-
"""L1 路由 · dashboard_router —— 风控大盘

对应教学宝典：
    * 第 12 章 12.2 第 3 类「告警阈值」：待审核堆积 / 规则命中率下限 / 黑名单命中率上限
    * 第 11 章工具 5/6/7：query_dashboard_stats / analyze_risk_trend / analyze_rule_effectiveness

端点（3 个）：
    GET    /api/dashboard/stats                核心指标 + 告警判定
    GET    /api/dashboard/trend                风险趋势（按天，可指定 days）
    GET    /api/dashboard/rule-effectiveness   规则命中率分析（含 0 命中的"僵尸规则"）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.config import settings
from app.database import Session, pool
from app.engine import ml_model
from app.framework import Request, Router
from app.models import CASE_STATUSES, DECISIONS, EVENT_TYPES, RISK_LEVELS, RULE_CATEGORIES

logger = logging.getLogger("ai_risk.routers.dashboard")

router = Router(prefix="/api/dashboard", tags=["风控大盘"], name="dashboard_router")


def _db() -> Session:
    return Session(pool.acquire())


def _hist(db: Session, sql: str, keys: Any, params: Any = ()) -> Dict[str, int]:
    rows = db.fetch_all(sql, params)
    out = {k: 0 for k in keys}
    for row in rows:
        key = row.get("k")
        if key is None:
            continue
        out[str(key)] = int(row.get("cnt") or 0)
    return out


# ====================================================================== 1
@router.get("/stats", "核心指标 + 三类告警判定")
def stats(request: Request) -> Dict[str, Any]:
    window = max(request.q_int("window_hours", settings.ALERT_CHECK_WINDOW_HOURS), 1)
    since = (datetime.now() - timedelta(hours=window)).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    db = _db()
    try:
        total_events = db.scalar("SELECT COUNT(*) FROM risk_event")
        total_assessments = db.scalar("SELECT COUNT(*) FROM risk_assessment")
        today_events = db.scalar("SELECT COUNT(*) FROM risk_event WHERE date(event_time) = ?", [today])
        window_events = db.scalar("SELECT COUNT(*) FROM risk_event WHERE event_time >= ?", [since])

        decision_hist = _hist(
            db, "SELECT decision AS k, COUNT(*) AS cnt FROM risk_assessment GROUP BY decision",
            DECISIONS)
        level_hist = _hist(
            db, "SELECT risk_level AS k, COUNT(*) AS cnt FROM risk_assessment GROUP BY risk_level",
            RISK_LEVELS)
        event_hist = _hist(
            db, "SELECT event_type AS k, COUNT(*) AS cnt FROM risk_event GROUP BY event_type",
            EVENT_TYPES)
        case_hist = _hist(
            db, "SELECT case_status AS k, COUNT(*) AS cnt FROM risk_case "
                "WHERE deleted_at IS NULL GROUP BY case_status", CASE_STATUSES)

        avg_score = float(db.scalar("SELECT COALESCE(AVG(final_score),0) FROM risk_assessment"))
        max_score = float(db.scalar("SELECT COALESCE(MAX(final_score),0) FROM risk_assessment"))
        avg_cost = float(db.scalar("SELECT COALESCE(AVG(cost_ms),0) FROM risk_assessment"))
        veto_count = db.scalar("SELECT COUNT(*) FROM risk_assessment WHERE is_veto = 1")
        hit_assessments = db.scalar("SELECT COUNT(*) FROM risk_assessment WHERE hit_rule_count > 0")

        rules_total = db.scalar("SELECT COUNT(*) FROM risk_rule WHERE deleted_at IS NULL")
        rules_enabled = db.scalar(
            "SELECT COUNT(*) FROM risk_rule WHERE deleted_at IS NULL AND is_enabled = 1")
        blacklist_total = db.scalar(
            "SELECT COUNT(*) FROM risk_blacklist WHERE deleted_at IS NULL AND is_enabled = 1")
        blacklist_hits = db.scalar(
            "SELECT COALESCE(SUM(hit_count),0) FROM risk_blacklist WHERE deleted_at IS NULL")
        profiles_total = db.scalar("SELECT COUNT(*) FROM risk_user_profile")
        users_total = db.scalar("SELECT COUNT(*) FROM user_info")
        labeled = db.scalar("SELECT COUNT(*) FROM risk_assessment WHERE label IS NOT NULL")

        top_rules = db.fetch_all(
            "SELECT rule_id, rule_name, rule_category, risk_level, risk_score, hit_count "
            "FROM risk_rule WHERE deleted_at IS NULL AND hit_count > 0 "
            "ORDER BY hit_count DESC LIMIT 10")
        top_users = db.fetch_all(
            """SELECT p.user_id, u.user_name, p.total_events, p.risk_event_count,
                      p.max_final_score, p.avg_final_score, p.profile_level, p.last_decision
               FROM risk_user_profile p LEFT JOIN user_info u ON u.user_id = p.user_id
               ORDER BY p.max_final_score DESC, p.risk_event_count DESC LIMIT 10""")
        recent = db.fetch_all(
            """SELECT a.assessment_id, a.user_id, u.user_name, a.event_type, a.source_id,
                      a.final_score, a.risk_level, a.decision, a.is_veto, a.create_time
               FROM risk_assessment a LEFT JOIN user_info u ON u.user_id = a.user_id
               ORDER BY a.create_time DESC, a.assessment_id DESC LIMIT 10""")
    finally:
        db.close()

    rule_hit_rate = round(hit_assessments / total_assessments * 100, 2) if total_assessments else 0.0
    blacklist_hit_rate = round(blacklist_hits / total_assessments * 100, 2) if total_assessments else 0.0
    pending = case_hist.get("待审核", 0)

    # ---------------- 宝典 12.2 第 3 类：三条告警 ----------------
    alerts: List[Dict[str, Any]] = []
    if pending > settings.ALERT_PENDING_CASE_THRESHOLD:
        alerts.append({"level": "警告", "type": "案件堆积",
                       "message": f"待审核案件 {pending} 个，超过阈值 "
                                  f"{settings.ALERT_PENDING_CASE_THRESHOLD}",
                       "field": "ALERT_PENDING_CASE_THRESHOLD"})
    if total_assessments >= 20 and rule_hit_rate < settings.ALERT_RULE_HIT_RATE_MIN:
        alerts.append({"level": "警告", "type": "规则失效",
                       "message": f"规则命中率 {rule_hit_rate}%，低于下限 "
                                  f"{settings.ALERT_RULE_HIT_RATE_MIN}%，规则可能已失效",
                       "field": "ALERT_RULE_HIT_RATE_MIN"})
    if blacklist_hit_rate > settings.ALERT_BLACKLIST_HIT_RATE_MAX:
        alerts.append({"level": "严重", "type": "疑似攻击",
                       "message": f"黑名单命中率 {blacklist_hit_rate}%，高于上限 "
                                  f"{settings.ALERT_BLACKLIST_HIT_RATE_MAX}%，可能正被批量攻击",
                       "field": "ALERT_BLACKLIST_HIT_RATE_MAX"})

    return {"success": True, "data": {
        "overview": {
            "total_events": total_events, "total_assessments": total_assessments,
            "today_events": today_events, "window_events": window_events,
            "window_hours": window,
            "avg_final_score": round(avg_score, 2), "max_final_score": round(max_score, 2),
            "avg_cost_ms": round(avg_cost, 1),
            "veto_count": veto_count, "veto_rate":
                round(veto_count / total_assessments * 100, 2) if total_assessments else 0.0,
            "rule_hit_rate": rule_hit_rate, "blacklist_hit_rate": blacklist_hit_rate,
            "rules_total": rules_total, "rules_enabled": rules_enabled,
            "blacklist_total": blacklist_total, "blacklist_hits": blacklist_hits,
            "profiles_total": profiles_total, "users_total": users_total,
            "labeled_samples": labeled,
            "pending_cases": pending,
            "active_cases": pending + case_hist.get("审核中", 0),
        },
        "decision_histogram": decision_hist,
        "risk_level_histogram": level_hist,
        "event_type_histogram": event_hist,
        "case_status_histogram": case_hist,
        "top_rules": top_rules,
        "top_risk_users": top_users,
        "recent_assessments": recent,
        "alerts": alerts,
        "model": ml_model.model_status(),
        "thresholds": {
            "pass": settings.RISK_PASS_THRESHOLD, "mark": settings.RISK_MARK_THRESHOLD,
            "review": settings.RISK_REVIEW_THRESHOLD, "veto_min": settings.RISK_VETO_MIN_SCORE,
            "weight_rule": settings.ML_WEIGHT_RULE, "weight_ml": settings.ML_WEIGHT_XGB,
        },
    }}


# ====================================================================== 2
@router.get("/trend", "风险趋势（按天）")
def trend(request: Request) -> Dict[str, Any]:
    days = min(max(request.q_int("days", 14), 1), 90)
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    db = _db()
    try:
        rows = db.fetch_all(
            """SELECT date(create_time) AS d,
                      COUNT(*) AS total,
                      SUM(CASE WHEN decision = '通过' THEN 1 ELSE 0 END) AS pass_cnt,
                      SUM(CASE WHEN decision = '标记' THEN 1 ELSE 0 END) AS mark_cnt,
                      SUM(CASE WHEN decision = '人工审核' THEN 1 ELSE 0 END) AS review_cnt,
                      SUM(CASE WHEN decision = '拒绝' THEN 1 ELSE 0 END) AS reject_cnt,
                      SUM(CASE WHEN is_veto = 1 THEN 1 ELSE 0 END) AS veto_cnt,
                      SUM(CASE WHEN hit_rule_count > 0 THEN 1 ELSE 0 END) AS hit_cnt,
                      COALESCE(AVG(final_score),0) AS avg_score,
                      COALESCE(MAX(final_score),0) AS max_score
               FROM risk_assessment WHERE date(create_time) >= ?
               GROUP BY date(create_time) ORDER BY d""", [start])
        case_rows = db.fetch_all(
            "SELECT date(create_time) AS d, COUNT(*) AS cnt FROM risk_case "
            "WHERE date(create_time) >= ? AND deleted_at IS NULL GROUP BY date(create_time)",
            [start])
    finally:
        db.close()

    by_day = {r["d"]: r for r in rows}
    case_by_day = {r["d"]: r["cnt"] for r in case_rows}
    series: List[Dict[str, Any]] = []
    for i in range(days):
        day = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        row = by_day.get(day)
        total = int(row["total"]) if row else 0
        series.append({
            "date": day, "total": total,
            "通过": int(row["pass_cnt"]) if row else 0,
            "标记": int(row["mark_cnt"]) if row else 0,
            "人工审核": int(row["review_cnt"]) if row else 0,
            "拒绝": int(row["reject_cnt"]) if row else 0,
            "veto": int(row["veto_cnt"]) if row else 0,
            "cases": int(case_by_day.get(day, 0)),
            "avg_score": round(float(row["avg_score"]), 2) if row else 0.0,
            "max_score": round(float(row["max_score"]), 2) if row else 0.0,
            "hit_rate": round(int(row["hit_cnt"]) / total * 100, 2) if total else 0.0,
        })

    total_all = sum(s["total"] for s in series)
    reject_all = sum(s["拒绝"] for s in series)
    return {"success": True, "days": days, "series": series, "summary": {
        "total": total_all, "reject": reject_all,
        "reject_rate": round(reject_all / total_all * 100, 2) if total_all else 0.0,
        "peak_day": max(series, key=lambda s: s["total"])["date"] if series else "",
        "avg_per_day": round(total_all / days, 2),
    }}


# ====================================================================== 3
@router.get("/rule-effectiveness", "规则命中率分析（含僵尸规则）")
def rule_effectiveness(request: Request) -> Dict[str, Any]:
    db = _db()
    try:
        rules = db.fetch_all(
            """SELECT rule_id, rule_name, rule_category, event_type, risk_level, risk_score,
                      action, is_enabled, priority, hit_count
               FROM risk_rule WHERE deleted_at IS NULL
               ORDER BY hit_count DESC, priority DESC""")
        total_assessments = db.scalar("SELECT COUNT(*) FROM risk_assessment")
    finally:
        db.close()

    total_hits = sum(int(r["hit_count"] or 0) for r in rules)
    for row in rules:
        hits = int(row["hit_count"] or 0)
        row["hit_share"] = round(hits / total_hits * 100, 2) if total_hits else 0.0
        row["coverage"] = round(hits / total_assessments * 100, 2) if total_assessments else 0.0
        row["is_zombie"] = hits == 0 and int(row["is_enabled"] or 0) == 1
        row["is_veto"] = row["risk_level"] == "极高"

    by_category: Dict[str, Dict[str, Any]] = {
        c: {"category": c, "rules": 0, "enabled": 0, "hits": 0, "zombie": 0}
        for c in RULE_CATEGORIES}
    for row in rules:
        bucket = by_category.setdefault(
            row["rule_category"] or "未分类",
            {"category": row["rule_category"] or "未分类", "rules": 0, "enabled": 0,
             "hits": 0, "zombie": 0})
        bucket["rules"] += 1
        bucket["enabled"] += int(row["is_enabled"] or 0)
        bucket["hits"] += int(row["hit_count"] or 0)
        bucket["zombie"] += 1 if row["is_zombie"] else 0

    zombies = [r["rule_id"] for r in rules if r["is_zombie"]]
    overall_rate = round(total_hits / total_assessments * 100, 2) if total_assessments else 0.0
    return {"success": True, "data": {
        "rules": rules,
        "by_category": list(by_category.values()),
        "total_rules": len(rules),
        "total_hits": total_hits,
        "total_assessments": total_assessments,
        "overall_hit_rate": overall_rate,
        "zombie_rules": zombies,
        "zombie_count": len(zombies),
        "alert": overall_rate < settings.ALERT_RULE_HIT_RATE_MIN and total_assessments >= 20,
        "alert_threshold": settings.ALERT_RULE_HIT_RATE_MIN,
    }}
