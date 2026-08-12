# -*- coding: utf-8 -*-
"""事件服务 —— 对应教学宝典《第 4 章：核心引擎 7 步流水线》

## 7 步 + 9 个内部函数（宝典 4.2）
| 步骤 | 函数 | 职责 |
|------|------|------|
| 1a | `_validate_request`     | 调 6 个 ensure_*（防越权）|
| 1b | `_build_context`        | 构造 ctx dict |
| 1c | `_enrich_receive_id`    | 补全收货地址 ID |
| 2  | `_create_event_record`  | 插入 risk_event 拿 event_id |
| 3  | `_compute_features`     | 25 维特征 |
| 4  | `_save_feature_snapshot`| 25 条 risk_feature |
| 5  | `_evaluate_rules`       | 加载规则 + 匹配 + 包装成 hits |
| 6  | `_calculate_decision`   | 双轨融合 + 一票否决 |
| 7  | `_save_assessment` + `_maybe_create_case` + `_update_user_profile` | 落库 4-5 张表 |

## 关键设计（宝典 4.3）
`process_event` 末尾 `db.commit()` —— **整个流程一个事务**，任何步骤失败 → 全部回滚。
🛂 旅客"过安检"是一个完整动作：要么全过（完整档案），要么全不过（不留记录）。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import settings
from app.engine import decision as decision_engine
from app.engine import feature as feature_engine
from app.engine import rule as rule_engine
from app.service import validator
from app.service.action_log import record_action

logger = logging.getLogger("ai_risk.service.event")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


# ====================================================================== 步骤 1a
def _validate_request(db: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """调 6 个 ensure_*（宝典 4.2 / 第 10 章）。"""
    return validator.validate_risk_check_request(db, payload)


# ====================================================================== 步骤 1b
def _build_context(validated: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """构造 ctx dict —— 后续所有步骤只认 ctx，不再回头看原始 payload。"""
    event_time = payload.get("event_time") or _now_str()
    return {
        "event_id": _new_id("EVT"),
        "event_type": validated["event_type"],
        "user_id": validated["user_id"],
        "source_id": validated["source_id"],
        "order_id": validated.get("order_id"),
        "receive_id": validated.get("receive_id"),
        "event_time": event_time,
        "client_ip": payload.get("client_ip") or validated.get("client_ip") or "",
        "device_id": payload.get("device_id") or validated.get("device_id") or "",
        "user": validated.get("user") or {},
        "order": validated.get("order") or {},
        "source_row": validated.get("source_row") or {},
        "remark": payload.get("remark") or "",
        "checks": validated.get("_checks") or [],
    }


# ====================================================================== 步骤 1c
def _enrich_receive_id(db: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """补全收货地址 ID：请求没传 → 从订单取 → 再没有就取用户默认地址。"""
    if ctx.get("receive_id"):
        return ctx
    order_id = ctx.get("order_id")
    if order_id:
        row = db.fetch_one("SELECT receive_id FROM order_info WHERE order_id = ?", [order_id])
        if row and row.get("receive_id"):
            ctx["receive_id"] = row["receive_id"]
            return ctx
    row = db.fetch_one(
        "SELECT address_id FROM user_address WHERE user_id = ? AND deleted_at IS NULL "
        "ORDER BY is_default DESC, create_time DESC LIMIT 1", [ctx["user_id"]])
    if row:
        ctx["receive_id"] = row["address_id"]
    return ctx


# ====================================================================== 步骤 2
def _create_event_record(db: Any, ctx: Dict[str, Any]) -> str:
    """插入 risk_event 拿 event_id。"""
    event_data = {
        "user_name": (ctx.get("user") or {}).get("user_name"),
        "order_amount": (ctx.get("order") or {}).get("total_amount"),
        "order_status": (ctx.get("order") or {}).get("order_status"),
        "remark": ctx.get("remark"),
    }
    db.insert("risk_event", {
        "event_id": ctx["event_id"],
        "event_type": ctx["event_type"],
        "user_id": ctx["user_id"],
        "source_id": ctx["source_id"],
        "order_id": ctx.get("order_id"),
        "receive_id": ctx.get("receive_id"),
        "event_data": json.dumps(event_data, ensure_ascii=False, default=str),
        "client_ip": ctx.get("client_ip"),
        "device_id": ctx.get("device_id"),
        "event_time": ctx["event_time"],
        "create_time": _now_str(),
    })
    return ctx["event_id"]


# ====================================================================== 步骤 3
def _compute_features(db: Any, ctx: Dict[str, Any]) -> Dict[str, float]:
    return feature_engine.compute_all_features(db, ctx)


# ====================================================================== 步骤 4
def _save_feature_snapshot(db: Any, event_id: str, features: Dict[str, float]) -> int:
    """25 维 → 25 条 risk_feature（快照，训练 ML 用它，不受业务数据变化影响）。"""
    rows = feature_engine.build_feature_rows(event_id, features)
    return db.insert_many("risk_feature", rows)


# ====================================================================== 步骤 5
def _evaluate_rules(db: Any, ctx: Dict[str, Any], features: Dict[str, float]) -> Dict[str, Any]:
    """加载规则 + 匹配 + 包装成 hits，并附加黑名单撞黑检查。"""
    rules = rule_engine.load_enabled_rules(db, ctx["event_type"])
    hits = rule_engine.match(rules, features)
    blacklist_hits = _check_blacklist(db, ctx)
    return {"rules_loaded": len(rules), "hits": hits + blacklist_hits,
            "rule_hits": hits, "blacklist_hits": blacklist_hits}


def _check_blacklist(db: Any, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """黑名单撞黑 → 系统级一票否决（不属于 30 条规则，risk_level=极高）。

    🛂 类比：失信旅客名单 —— 名单上的人直接扣留。
    """
    candidates: List[tuple[str, Optional[str]]] = [
        ("用户", ctx.get("user_id")),
        ("手机号", (ctx.get("user") or {}).get("phone")),
        ("地址", ctx.get("receive_id")),
        ("设备", ctx.get("device_id") or None),
        ("IP", ctx.get("client_ip") or None),
    ]
    hits: List[Dict[str, Any]] = []
    now = _now_str()
    for blacklist_type, value in candidates:
        if not value:
            continue
        row = db.fetch_one(
            "SELECT * FROM risk_blacklist WHERE blacklist_type = ? AND blacklist_value = ? "
            "AND is_enabled = 1 AND deleted_at IS NULL "
            "AND (expire_time IS NULL OR expire_time = '' OR expire_time > ?)",
            [blacklist_type, str(value), now])
        if not row:
            continue
        db.update("risk_blacklist", {"hit_count": int(row.get("hit_count") or 0) + 1},
                  "blacklist_id = ?", [row["blacklist_id"]])
        hits.append({
            "rule_id": f"BL{int(row['blacklist_id']):03d}",
            "rule_name": f"黑名单命中（{blacklist_type}）",
            "rule_category": "黑名单",
            "risk_level": row.get("risk_level") or "极高",
            "risk_score": 100 if (row.get("risk_level") or "极高") == "极高" else 80,
            "action": "拒绝",
            "priority": 999,
            "condition": {"field": f"blacklist.{blacklist_type}", "op": "==", "value": str(value)},
            "description": row.get("reason") or "命中黑名单",
            "is_blacklist": True,
        })
    return hits


# ====================================================================== 步骤 6
def _calculate_decision(features: Dict[str, float], hits: List[Dict[str, Any]],
                        explain: bool = False) -> Dict[str, Any]:
    return decision_engine.calculate(features, hits, explain=explain)


# ====================================================================== 步骤 7
#: 宝典 7.11 label 三来源之「方式 3 规则反推」——教学环境默认来源
LABEL_SOURCE_RULE = "规则反推"


def derive_label(final_score: Any) -> int:
    """规则反推 label：final_score >= XGB_LABEL_SCORE_THRESHOLD(80) → 正样本。

    单独抽成函数是为了让「落库的 label」和「返回给调用方的 label」永远同源 ——
    以前 `process_event()` 的返回值里漏了 label，导致 `gen_risk_data.py` 的
    `--target-pos-ratio` 自适应采样拿不到真实标签、反馈环失效（永远抽 hot 池）。
    """
    return 1 if int(final_score) >= settings.XGB_LABEL_SCORE_THRESHOLD else 0


def _save_assessment(db: Any, ctx: Dict[str, Any], features: Dict[str, float],
                     result: Dict[str, Any], cost_ms: int) -> str:
    assessment_id = _new_id("ASS")
    label = derive_label(result["final_score"])
    db.insert("risk_assessment", {
        "assessment_id": assessment_id,
        "event_id": ctx["event_id"],
        "user_id": ctx["user_id"],
        "event_type": ctx["event_type"],
        "source_id": ctx["source_id"],
        "rule_score": result["rule_score"],
        "ml_score": result["ml_score"],
        "ml_probability": result["ml_probability"],
        "final_score": result["final_score"],
        "risk_level": result["risk_level"],
        "decision": result["decision"],
        "hit_rules": json.dumps(result["hit_rules"], ensure_ascii=False, default=str),
        "hit_rule_count": result["hit_rule_count"],
        "is_veto": result["is_veto"],
        "ml_loaded": result["ml_loaded"],
        "weight_rule": result["weight_rule"],
        "weight_ml": result["weight_ml"],
        "feature_snapshot": json.dumps(features, ensure_ascii=False),
        "reason": result["reason"][:500],
        "cost_ms": cost_ms,
        "label": label,
        "label_source": LABEL_SOURCE_RULE,   # 宝典 7.11 教学版方式 3
        "create_time": _now_str(),
    })
    # 规则命中计数（规则命中率分析用）
    for hit in result["hit_rules"]:
        if hit.get("is_blacklist"):
            continue
        db.execute("UPDATE risk_rule SET hit_count = hit_count + 1 WHERE rule_id = ?", [hit["rule_id"]])
    return assessment_id


def _maybe_create_case(db: Any, ctx: Dict[str, Any], assessment_id: str,
                       result: Dict[str, Any]) -> Optional[str]:
    """宝典 9.3：只有「人工审核 / 拒绝」生成 risk_case。"""
    if not result["need_case"]:
        return None
    case_id = _new_id("CASE")
    db.insert("risk_case", {
        "case_id": case_id,
        "assessment_id": assessment_id,
        "event_id": ctx["event_id"],
        "user_id": ctx["user_id"],
        "source_id": ctx["source_id"],
        "event_type": ctx["event_type"],
        "case_status": "待审核",
        "risk_level": result["risk_level"],
        "final_score": result["final_score"],
        "decision": result["decision"],
        "hit_rules": json.dumps([h["rule_id"] for h in result["hit_rules"]], ensure_ascii=False),
        "create_time": _now_str(),
        "update_time": _now_str(),
    })
    record_action(db, operator="system", action_type="案件创建", target_type="案件",
                  target_id=case_id, after_value={"case_status": "待审核",
                                                  "final_score": result["final_score"]},
                  remark=f"决策={result['decision']} 自动建案")
    return case_id


def _update_user_profile(db: Any, ctx: Dict[str, Any], result: Dict[str, Any],
                         case_created: bool, blacklist_hit: int) -> None:
    """UPSERT risk_user_profile（每用户 1 条，宝典 16 章 1:1）。"""
    user_id = ctx["user_id"]
    row = db.fetch_one("SELECT * FROM risk_user_profile WHERE user_id = ?", [user_id])
    decision = result["decision"]
    score = result["final_score"]
    counters = {"通过": "pass_count", "标记": "mark_count",
                "人工审核": "review_count", "拒绝": "reject_count"}

    if row is None:
        values = {
            "user_id": user_id, "total_events": 1,
            "risk_event_count": 1 if decision in ("人工审核", "拒绝") else 0,
            "pass_count": 0, "mark_count": 0, "review_count": 0, "reject_count": 0,
            "case_count": 1 if case_created else 0,
            "blacklist_hit_count": blacklist_hit,
            "last_risk_level": result["risk_level"], "last_decision": decision,
            "last_final_score": score, "max_final_score": score, "avg_final_score": score,
            "profile_level": result["risk_level"],
            "last_event_time": ctx["event_time"], "update_time": _now_str(),
        }
        values[counters[decision]] = 1
        db.insert("risk_user_profile", values)
        return

    total = int(row.get("total_events") or 0) + 1
    avg = ((float(row.get("avg_final_score") or 0) * (total - 1)) + score) / total
    values = {
        "total_events": total,
        "risk_event_count": int(row.get("risk_event_count") or 0) + (1 if decision in ("人工审核", "拒绝") else 0),
        "case_count": int(row.get("case_count") or 0) + (1 if case_created else 0),
        "blacklist_hit_count": int(row.get("blacklist_hit_count") or 0) + blacklist_hit,
        "last_risk_level": result["risk_level"], "last_decision": decision,
        "last_final_score": score,
        "max_final_score": max(int(row.get("max_final_score") or 0), score),
        "avg_final_score": round(avg, 2),
        "profile_level": decision_engine.score_to_risk_level(
            max(int(row.get("max_final_score") or 0), score)),
        "last_event_time": ctx["event_time"], "update_time": _now_str(),
    }
    values[counters[decision]] = int(row.get(counters[decision]) or 0) + 1
    db.update("risk_user_profile", values, "user_id = ?", [user_id])


# ====================================================================== 主流程
def process_event(db: Any, payload: Dict[str, Any], operator: str = "api",
                  explain: bool = True) -> Dict[str, Any]:
    """7 步流水线主入口 —— **一个事务**，末尾一次 commit（宝典 4.3）。"""
    started = time.time()
    timeline: List[Dict[str, Any]] = []

    def mark(step: str, name: str, detail: str) -> None:
        timeline.append({"step": step, "name": name, "detail": detail,
                         "elapsed_ms": int((time.time() - started) * 1000)})

    # ---------------- 步骤 1：校验 + 上下文 ----------------
    validated = _validate_request(db, payload)
    mark("1a", "请求校验（6 个 ensure_*）", "全部通过，横向越权防护生效")

    ctx = _build_context(validated, payload)
    mark("1b", "构造上下文 ctx", f"event_id={ctx['event_id']} type={ctx['event_type']}")

    ctx = _enrich_receive_id(db, ctx)
    mark("1c", "补全收货地址", f"receive_id={ctx.get('receive_id') or '无'}")

    # ---------------- 步骤 2：事件落库 ----------------
    event_id = _create_event_record(db, ctx)
    mark("2", "INSERT risk_event", f"event_id={event_id}")

    # ---------------- 步骤 3-4：特征 + 快照 ----------------
    features = _compute_features(db, ctx)
    mark("3", "计算 25 维特征", f"用户 14 + 订单 8 + 地址 3 = {len(features)} 维")

    saved = _save_feature_snapshot(db, event_id, features)
    mark("4", "INSERT risk_feature", f"写入 {saved} 条特征快照")

    # ---------------- 步骤 5：规则匹配 ----------------
    rule_result = _evaluate_rules(db, ctx, features)
    mark("5", "规则引擎匹配",
         f"加载 {rule_result['rules_loaded']} 条规则，命中 {len(rule_result['rule_hits'])} 条"
         + (f" + 黑名单 {len(rule_result['blacklist_hits'])} 条" if rule_result["blacklist_hits"] else ""))

    # ---------------- 步骤 6：双轨融合 ----------------
    result = _calculate_decision(features, rule_result["hits"], explain=explain)
    mark("6", "双轨融合 + 一票否决",
         f"规则 {result['rule_score']} / 模型 {result['ml_score']} → 融合 {result['final_score']}"
         + ("（一票否决）" if result["is_veto"] else ""))

    # ---------------- 步骤 7：落库 4-5 张表 ----------------
    cost_ms = int((time.time() - started) * 1000)
    assessment_id = _save_assessment(db, ctx, features, result, cost_ms)
    case_id = _maybe_create_case(db, ctx, assessment_id, result)
    _update_user_profile(db, ctx, result, case_created=bool(case_id),
                         blacklist_hit=len(rule_result["blacklist_hits"]))
    record_action(db, operator=operator, action_type="风控检查", target_type="评估",
                  target_id=assessment_id,
                  after_value={"decision": result["decision"], "final_score": result["final_score"]},
                  remark=f"{ctx['event_type']} / {ctx['source_id']}")
    mark("7", "落库并提交事务",
         f"risk_assessment + {'risk_case + ' if case_id else ''}risk_user_profile + 审计日志")

    db.commit()   # ⚠️ 整个 7 步一个事务：要么全过，要么全不过

    return {
        "event_id": event_id,
        "assessment_id": assessment_id,
        "case_id": case_id,
        "event_type": ctx["event_type"],
        "user_id": ctx["user_id"],
        "source_id": ctx["source_id"],
        "order_id": ctx.get("order_id"),
        "receive_id": ctx.get("receive_id"),
        "rule_score": result["rule_score"],
        "ml_score": result["ml_score"],
        "ml_probability": result["ml_probability"],
        "ml_loaded": bool(result["ml_loaded"]),
        "ml_reason": result["ml_reason"],
        "ml_decision": result["ml_decision"],
        "ml_contributions": result["ml_contributions"],
        "fused_score": result["fused_score"],
        "final_score": result["final_score"],
        "risk_level": result["risk_level"],
        "decision": result["decision"],
        "is_veto": bool(result["is_veto"]),
        "veto_rules": result["veto_rules"],
        "reason": result["reason"],
        "hit_rules": result["hit_rules"],
        "hit_rule_count": result["hit_rule_count"],
        "rules_loaded": rule_result["rules_loaded"],
        "blacklist_hits": rule_result["blacklist_hits"],
        "features": features,
        "feature_defs": feature_engine.FEATURE_DEFS,
        "fusion_steps": result["steps"],
        "validate_checks": ctx["checks"],
        "timeline": timeline,
        "cost_ms": cost_ms,
        "need_case": result["need_case"],
        # 训练集标签（与 risk_assessment 落库值同源，gen_risk_data.py 自适应采样依赖它）
        "label": derive_label(result["final_score"]),
        "label_source": LABEL_SOURCE_RULE,
    }


# ====================================================================== 查询辅助
def list_assessments(db: Any, user_id: str = "", decision: str = "", risk_level: str = "",
                     event_type: str = "", keyword: str = "",
                     limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    where: List[str] = ["1=1"]
    params: List[Any] = []
    if user_id:
        where.append("a.user_id = ?")
        params.append(user_id)
    if decision:
        where.append("a.decision = ?")
        params.append(decision)
    if risk_level:
        where.append("a.risk_level = ?")
        params.append(risk_level)
    if event_type:
        where.append("a.event_type = ?")
        params.append(event_type)
    if keyword:
        where.append("(a.assessment_id LIKE ? OR a.source_id LIKE ? OR a.user_id LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    clause = " AND ".join(where)
    total = db.scalar(f"SELECT COUNT(*) FROM risk_assessment a WHERE {clause}", params)
    rows = db.fetch_all(
        f"""SELECT a.*, u.user_name
            FROM risk_assessment a LEFT JOIN user_info u ON u.user_id = a.user_id
            WHERE {clause} ORDER BY a.create_time DESC, a.assessment_id DESC LIMIT ? OFFSET ?""",
        params + [limit, offset])
    for row in rows:
        row["hit_rules"] = _safe_json(row.get("hit_rules"), [])
        row.pop("feature_snapshot", None)
    return {"total": total, "items": rows, "limit": limit, "offset": offset}


def get_assessment_detail(db: Any, assessment_id: str) -> Optional[Dict[str, Any]]:
    row = db.fetch_one(
        """SELECT a.*, u.user_name, e.event_time, e.client_ip, e.device_id, e.event_data,
                  e.receive_id, e.order_id
           FROM risk_assessment a
           LEFT JOIN user_info u ON u.user_id = a.user_id
           LEFT JOIN risk_event e ON e.event_id = a.event_id
           WHERE a.assessment_id = ?""", [assessment_id])
    if not row:
        return None
    row["hit_rules"] = _safe_json(row.get("hit_rules"), [])
    row["feature_snapshot"] = _safe_json(row.get("feature_snapshot"), {})
    row["event_data"] = _safe_json(row.get("event_data"), {})
    row["features"] = db.fetch_all(
        "SELECT feature_name, feature_value, feature_dim FROM risk_feature "
        "WHERE event_id = ? ORDER BY feature_id", [row["event_id"]])
    row["case"] = db.fetch_one(
        "SELECT case_id, case_status, reviewer, review_comment FROM risk_case "
        "WHERE assessment_id = ? AND deleted_at IS NULL", [assessment_id])
    return row


def get_event_features(db: Any, event_id: str) -> List[Dict[str, Any]]:
    return db.fetch_all(
        "SELECT feature_name, feature_value, feature_dim FROM risk_feature "
        "WHERE event_id = ? ORDER BY feature_id", [event_id])


def _safe_json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
