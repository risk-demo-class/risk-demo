# -*- coding: utf-8 -*-
"""L1 路由 · rule_router —— 规则管理（违禁品清单）

对应教学宝典第 6 章「规则引擎」：
    * 30 条预置规则 / 6 大类
    * 14 种 op 的 JSON 条件表达式
    * 软删（`deleted_at`，2026-08-07 加）而非物理删除
    * 未知 op / 未知 field 兜底不命中

端点（5 个）：
    GET    /api/rules              规则列表（含 meta：14 op / 25 特征 / 6 大类）
    POST   /api/rules              新增规则（条件静态校验）
    PUT    /api/rules/{rule_id}    修改规则（记审计：before/after）
    DELETE /api/rules/{rule_id}    软删规则（deleted_at）
    POST   /api/rules/test         规则测试器（返回逐节点求值轨迹）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.data.rules_seed import CATEGORY_STATS
from app.database import Session, pool
from app.engine import feature as feature_engine
from app.engine import rule as rule_engine
from app.framework import HTTPError, Request, Router
from app.models import RISK_LEVELS, RULE_CATEGORIES
from app.service.action_log import record_action

logger = logging.getLogger("ai_risk.routers.rule")

router = Router(prefix="/api/rules", tags=["规则管理"], name="rule_router")

_ACTIONS = ("通过", "标记", "人工审核", "拒绝")


def _db() -> Session:
    return Session(pool.acquire())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _meta() -> Dict[str, Any]:
    """规则编辑器需要的全部元数据 —— 前端下拉框/提示全靠它。"""
    return {
        "ops": rule_engine.OP_DOC,
        "op_count": rule_engine.OP_COUNT,
        "features": feature_engine.FEATURE_DEFS,
        "feature_count": len(feature_engine.FEATURE_DEFS),
        "categories": list(RULE_CATEGORIES),
        "category_stats": CATEGORY_STATS,
        "risk_levels": list(RISK_LEVELS),
        "actions": list(_ACTIONS),
        "veto_level": "极高",
    }


def _normalize_condition(raw: Any) -> str:
    """条件入库前：dict/str → 校验 → 紧凑 JSON 文本。"""
    condition = raw
    if isinstance(raw, str):
        try:
            condition = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPError(400, f"rule_condition 不是合法 JSON: {exc}") from exc
    errors = rule_engine.validate_condition(condition)
    if errors:
        raise HTTPError(400, "规则条件非法：" + "；".join(errors))
    return json.dumps(condition, ensure_ascii=False)


# ====================================================================== 1
@router.get("", "规则列表（含 14 op / 25 特征元数据）")
def list_rules(request: Request) -> Dict[str, Any]:
    category = request.q("rule_category", "") or ""
    event_type = request.q("event_type", "") or ""
    keyword = request.q("keyword", "") or ""
    enabled = request.q("is_enabled", "")
    include_deleted = request.q_bool("include_deleted", False)

    where: List[str] = ["1=1"]
    params: List[Any] = []
    if not include_deleted:
        where.append("deleted_at IS NULL")          # 宝典 6.4：软删规则不参与
    if category:
        where.append("rule_category = ?")
        params.append(category)
    if event_type:
        where.append("(event_type = ? OR event_type IS NULL OR event_type = '')")
        params.append(event_type)
    if enabled not in (None, ""):
        where.append("is_enabled = ?")
        params.append(1 if str(enabled).lower() in ("1", "true", "yes") else 0)
    if keyword:
        where.append("(rule_id LIKE ? OR rule_name LIKE ? OR description LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    clause = " AND ".join(where)

    db = _db()
    try:
        rows = db.fetch_all(
            f"""SELECT * FROM risk_rule WHERE {clause}
                ORDER BY priority DESC, rule_id ASC""", params)
        total_hit = db.scalar("SELECT COALESCE(SUM(hit_count),0) FROM risk_rule")
    finally:
        db.close()

    for row in rows:
        row["rule_condition"] = rule_engine.parse_condition(row.get("rule_condition"))
        row["is_enabled"] = int(row.get("is_enabled") or 0)
        row["is_veto"] = row.get("risk_level") == "极高"
    return {
        "success": True,
        "total": len(rows),
        "items": rows,
        "total_hit_count": total_hit,
        "meta": _meta(),
    }


# ====================================================================== 2
@router.post("", "新增规则")
def create_rule(request: Request) -> Dict[str, Any]:
    payload = request.json()
    rule_id = str(payload.get("rule_id") or "").strip()
    rule_name = str(payload.get("rule_name") or "").strip()
    if not rule_id or not rule_name:
        raise HTTPError(400, "rule_id 与 rule_name 必填")
    category = str(payload.get("rule_category") or "")
    if category not in RULE_CATEGORIES:
        raise HTTPError(400, f"rule_category 必须是 {list(RULE_CATEGORIES)} 之一")
    risk_level = str(payload.get("risk_level") or "中")
    if risk_level not in RISK_LEVELS:
        raise HTTPError(400, f"risk_level 必须是 {list(RISK_LEVELS)} 之一")

    condition = _normalize_condition(payload.get("rule_condition"))
    operator = str(payload.get("operator") or "admin")
    values = {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "rule_category": category,
        "event_type": str(payload.get("event_type") or ""),
        "rule_condition": condition,
        "risk_level": risk_level,
        "risk_score": int(payload.get("risk_score") or 0),
        "action": str(payload.get("action") or "标记"),
        "is_enabled": 1 if payload.get("is_enabled", True) else 0,
        "priority": int(payload.get("priority") or 0),
        "description": str(payload.get("description") or ""),
        "hit_count": 0,
        "create_time": _now(),
        "update_time": _now(),
    }

    db = _db()
    try:
        exists = db.fetch_one("SELECT rule_id, deleted_at FROM risk_rule WHERE rule_id = ?", [rule_id])
        if exists and exists.get("deleted_at") is None:
            raise HTTPError(400, f"规则已存在: {rule_id}")
        if exists:                                   # 软删过的同 ID → 复活覆盖
            db.update("risk_rule", {k: v for k, v in values.items() if k != "rule_id"}
                      | {"deleted_at": None}, "rule_id = ?", [rule_id])
        else:
            db.insert("risk_rule", values)
        record_action(db, operator=operator, action_type="新增规则", target_type="规则",
                      target_id=rule_id, after_value=values, remark=rule_name)
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    finally:
        db.close()
    logger.info("新增规则 %s(%s) by %s", rule_id, rule_name, operator)
    return {"success": True, "data": values | {"rule_condition": json.loads(condition)}}


# ====================================================================== 3
@router.put("/{rule_id}", "修改规则（记审计 before/after）")
def update_rule(request: Request) -> Dict[str, Any]:
    rule_id = request.path_params["rule_id"]
    payload = request.json()
    operator = str(payload.get("operator") or "admin")

    editable = ("rule_name", "rule_category", "event_type", "risk_level", "risk_score",
                "action", "is_enabled", "priority", "description")
    values: Dict[str, Any] = {}
    for key in editable:
        if key not in payload:
            continue
        if key == "rule_category" and payload[key] not in RULE_CATEGORIES:
            raise HTTPError(400, f"rule_category 必须是 {list(RULE_CATEGORIES)} 之一")
        if key == "risk_level" and payload[key] not in RISK_LEVELS:
            raise HTTPError(400, f"risk_level 必须是 {list(RISK_LEVELS)} 之一")
        if key in ("risk_score", "priority"):
            values[key] = int(payload[key] or 0)
        elif key == "is_enabled":
            values[key] = 1 if payload[key] else 0
        else:
            values[key] = str(payload[key])
    if "rule_condition" in payload:
        values["rule_condition"] = _normalize_condition(payload["rule_condition"])
    if not values:
        raise HTTPError(400, "没有需要修改的字段")
    values["update_time"] = _now()

    db = _db()
    try:
        before = db.fetch_one("SELECT * FROM risk_rule WHERE rule_id = ? AND deleted_at IS NULL",
                              [rule_id])
        if not before:
            raise HTTPError(404, f"规则不存在: {rule_id}")
        db.update("risk_rule", values, "rule_id = ?", [rule_id])
        after = db.fetch_one("SELECT * FROM risk_rule WHERE rule_id = ?", [rule_id])
        record_action(db, operator=operator, action_type="修改规则", target_type="规则",
                      target_id=rule_id, before_value=before, after_value=after,
                      remark=str(payload.get("remark") or ""))
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    finally:
        db.close()
    after["rule_condition"] = rule_engine.parse_condition(after.get("rule_condition"))
    logger.info("修改规则 %s by %s: %s", rule_id, operator, list(values))
    return {"success": True, "data": after}


# ====================================================================== 4
@router.delete("/{rule_id}", "软删规则（deleted_at，不物理删除）")
def delete_rule(request: Request) -> Dict[str, Any]:
    rule_id = request.path_params["rule_id"]
    operator = request.q("operator", "") or request.headers.get("x-operator", "") or "admin"
    db = _db()
    try:
        before = db.fetch_one("SELECT * FROM risk_rule WHERE rule_id = ? AND deleted_at IS NULL",
                              [rule_id])
        if not before:
            raise HTTPError(404, f"规则不存在或已删除: {rule_id}")
        db.update("risk_rule", {"deleted_at": _now(), "is_enabled": 0, "update_time": _now()},
                  "rule_id = ?", [rule_id])
        record_action(db, operator=operator, action_type="删除规则", target_type="规则",
                      target_id=rule_id, before_value=before,
                      remark="软删除：历史命中记录保留可追溯")
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    finally:
        db.close()
    logger.info("软删规则 %s by %s", rule_id, operator)
    return {"success": True, "message": f"规则 {rule_id} 已软删除（历史可追溯）"}


# ====================================================================== 5
@router.post("/test", "规则测试器（14 op 逐节点求值轨迹）")
def test_rule(request: Request) -> Dict[str, Any]:
    """两种用法：
        1. 传 `rule_id` + `features` → 测已有规则
        2. 传 `rule_condition` + `features` → 测草稿条件（新增/修改前预演）
    """
    payload = request.json()
    features_in = payload.get("features") or {}
    if not isinstance(features_in, dict):
        raise HTTPError(400, "features 必须是 {特征名: 数值} 对象")

    # 缺失特征补 0，保证测试可跑（与真实流水线一致：unknown field 不命中）
    features: Dict[str, float] = {}
    for name, value in features_in.items():
        try:
            features[str(name)] = float(value)
        except (TypeError, ValueError):
            raise HTTPError(400, f"特征 {name} 的值不是数值: {value!r}") from None

    rule_id = str(payload.get("rule_id") or "").strip()
    rule_row: Dict[str, Any] = {}
    if rule_id:
        db = _db()
        try:
            rule_row = db.fetch_one(
                "SELECT * FROM risk_rule WHERE rule_id = ? AND deleted_at IS NULL", [rule_id]) or {}
        finally:
            db.close()
        if not rule_row:
            raise HTTPError(404, f"规则不存在: {rule_id}")
        condition = rule_engine.parse_condition(rule_row.get("rule_condition"))
    else:
        raw = payload.get("rule_condition")
        if raw in (None, ""):
            raise HTTPError(400, "需要 rule_id 或 rule_condition 之一")
        condition = raw if isinstance(raw, dict) else rule_engine.parse_condition(raw)
        errors = rule_engine.validate_condition(condition)
        if errors:
            return {"success": False, "valid": False, "errors": errors,
                    "hit": False, "trace": [], "meta": _meta()}

    hit, trace = rule_engine.evaluate_with_trace(condition, features)
    return {
        "success": True,
        "valid": True,
        "errors": [],
        "hit": hit,
        "trace": trace,
        "condition": condition,
        "rule": {k: rule_row.get(k) for k in
                 ("rule_id", "rule_name", "rule_category", "risk_level", "risk_score", "action")}
        if rule_row else None,
        "used_features": {k: features.get(k) for k in sorted(features)},
        "meta": _meta(),
    }
