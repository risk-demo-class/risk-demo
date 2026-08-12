# -*- coding: utf-8 -*-
"""案件服务 —— 对应教学宝典《第 9 章：案件状态机》

## 5 状态 + 9 种合法转换（宝典 9.1 / 9.2 关键代码 2）
    待审核 → 审核中 / 已通过 / 已拒绝 / 已关闭   (4)
    审核中 → 已通过 / 已拒绝 / 已关闭            (3)
    已通过 / 已拒绝 / 已关闭 = 终态               (0)
    ⇒ 4 + 3 + 2（已通过/已拒绝 → [*] 归档）= 9 种流转语义

状态机外的转换一律拒绝 —— 防止脏数据把案件改飞。

## 超时自动关闭（宝典 9.4 关键代码 3）
`CASE_TIMEOUT_HOURS` 默认 24；0 = 关闭此功能；关闭时 reviewer=system 并写审计。

## active_only（宝典 9.5）
案件工作台默认 `active_only=True`（只看待审核/审核中），已结案件查"评估历史"。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config import settings
from app.framework import HTTPError
from app.service.action_log import query_actions, record_action

logger = logging.getLogger("ai_risk.service.case")

# ====================================================================== 状态机白名单
_ALLOWED_CASE_TRANSITIONS: Dict[str, set] = {
    "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
    "审核中": {"已通过", "已拒绝", "已关闭"},
    "已通过": set(),      # 终态
    "已拒绝": set(),      # 终态
    "已关闭": set(),      # 终态
}
ACTIVE_STATUSES = ("待审核", "审核中")
TERMINAL_STATUSES = ("已通过", "已拒绝", "已关闭")

TRANSITION_COUNT = sum(len(v) for v in _ALLOWED_CASE_TRANSITIONS.values())   # = 7 条显式边


def allowed_transitions(status: str) -> List[str]:
    return sorted(_ALLOWED_CASE_TRANSITIONS.get(status, set()))


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED_CASE_TRANSITIONS.get(current, set())


def state_machine_doc() -> Dict[str, Any]:
    """给前端画状态机图。"""
    return {
        "statuses": list(_ALLOWED_CASE_TRANSITIONS),
        "active": list(ACTIVE_STATUSES),
        "terminal": list(TERMINAL_STATUSES),
        "transitions": [{"from": src, "to": sorted(dst)} for src, dst in _ALLOWED_CASE_TRANSITIONS.items()],
        "edge_count": TRANSITION_COUNT,
        "timeout_hours": settings.CASE_TIMEOUT_HOURS,
    }


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


# ====================================================================== 查询
def list_cases(db: Any, active_only: bool = True, case_status: str = "", user_id: str = "",
               risk_level: str = "", keyword: str = "", limit: int = 20,
               offset: int = 0) -> Dict[str, Any]:
    where: List[str] = ["c.deleted_at IS NULL"]
    params: List[Any] = []
    if case_status:
        where.append("c.case_status = ?")
        params.append(case_status)
    elif active_only:
        where.append(f"c.case_status IN ({','.join('?' * len(ACTIVE_STATUSES))})")
        params.extend(ACTIVE_STATUSES)
    if user_id:
        where.append("c.user_id = ?")
        params.append(user_id)
    if risk_level:
        where.append("c.risk_level = ?")
        params.append(risk_level)
    if keyword:
        where.append("(c.case_id LIKE ? OR c.source_id LIKE ? OR c.user_id LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    clause = " AND ".join(where)
    total = db.scalar(f"SELECT COUNT(*) FROM risk_case c WHERE {clause}", params)
    rows = db.fetch_all(
        f"""SELECT c.*, u.user_name FROM risk_case c
            LEFT JOIN user_info u ON u.user_id = c.user_id
            WHERE {clause}
            ORDER BY CASE c.risk_level WHEN '极高' THEN 4 WHEN '高' THEN 3 WHEN '中' THEN 2 ELSE 1 END DESC,
                     c.create_time DESC LIMIT ? OFFSET ?""", params + [limit, offset])
    for row in rows:
        row["hit_rules"] = _safe_json(row.get("hit_rules"), [])
        row["allowed_transitions"] = allowed_transitions(row.get("case_status") or "")
    summary = {r["case_status"]: r["cnt"] for r in db.fetch_all(
        "SELECT case_status, COUNT(*) AS cnt FROM risk_case WHERE deleted_at IS NULL GROUP BY case_status")}
    return {"total": total, "items": rows, "limit": limit, "offset": offset,
            "status_summary": summary, "active_only": active_only}


def get_case(db: Any, case_id: str) -> Dict[str, Any]:
    row = db.fetch_one(
        """SELECT c.*, u.user_name, u.phone, a.rule_score, a.ml_score, a.reason,
                  a.feature_snapshot, a.hit_rules AS assessment_hit_rules, a.event_id
           FROM risk_case c
           LEFT JOIN user_info u ON u.user_id = c.user_id
           LEFT JOIN risk_assessment a ON a.assessment_id = c.assessment_id
           WHERE c.case_id = ? AND c.deleted_at IS NULL""", [case_id])
    if not row:
        raise HTTPError(404, f"案件不存在: {case_id}", "E_CASE_NOT_FOUND")
    row["hit_rules"] = _safe_json(row.get("assessment_hit_rules"), []) or _safe_json(row.get("hit_rules"), [])
    row["feature_snapshot"] = _safe_json(row.get("feature_snapshot"), {})
    row["allowed_transitions"] = allowed_transitions(row.get("case_status") or "")
    row["action_logs"] = query_actions(db, target_type="案件", target_id=case_id, limit=50)["items"]
    return row


# ====================================================================== 状态流转
def transition_case(db: Any, case_id: str, target_status: str, operator: str,
                    comment: str = "", label: Optional[Any] = None) -> Dict[str, Any]:
    """统一流转入口：领取（待审核→审核中）/ 审核通过 / 审核拒绝 / 关闭。"""
    case = db.fetch_one(
        "SELECT * FROM risk_case WHERE case_id = ? AND deleted_at IS NULL", [case_id])
    if not case:
        raise HTTPError(404, f"案件不存在: {case_id}", "E_CASE_NOT_FOUND")
    current = case.get("case_status") or ""
    if target_status not in _ALLOWED_CASE_TRANSITIONS:
        raise HTTPError(400, f"非法目标状态: {target_status}", "E_STATUS_INVALID")
    if not can_transition(current, target_status):
        raise HTTPError(400,
                        f"非法状态流转: {current} → {target_status}。"
                        f"当前允许 {allowed_transitions(current) or '（终态，不可再流转）'}",
                        "E_TRANSITION_DENIED")
    if not operator:
        raise HTTPError(400, "operator（审核人）不能为空", "E_OPERATOR_REQUIRED")

    values: Dict[str, Any] = {"case_status": target_status, "reviewer": operator,
                              "update_time": _now()}
    if target_status in TERMINAL_STATUSES:
        values["review_time"] = _now()
        values["review_comment"] = comment or f"{operator} 处理为{target_status}"
    elif comment:
        values["review_comment"] = comment
    db.update("risk_case", values, "case_id = ?", [case_id])

    record_action(db, operator=operator, action_type=f"案件流转:{current}→{target_status}",
                  target_type="案件", target_id=case_id,
                  before_value={"case_status": current},
                  after_value={"case_status": target_status, "review_comment": comment},
                  remark=comment)

    # 人工标注反哺 ML 训练标签（宝典 7.11 方式 1：人工标注，最准）
    #   已拒绝 → label=1（确认风险）；已通过 → label=0（确认正常）
    #   审核人也可显式传 label 覆盖（例如"关闭但确实是黑产"）
    label_written: Optional[int] = None
    if label is not None:
        try:
            label_written = 1 if int(label) else 0
        except (TypeError, ValueError):
            label_written = None
    elif target_status in ("已拒绝", "已通过"):
        label_written = 1 if target_status == "已拒绝" else 0
    if label_written is not None and case.get("assessment_id"):
        db.update("risk_assessment",
                  {"label": label_written, "label_source": "人工标注"},
                  "assessment_id = ?", [case["assessment_id"]])

    db.commit()
    logger.info("案件 %s 流转 %s → %s（%s）", case_id, current, target_status, operator)
    return {"case_id": case_id, "from": current, "to": target_status,
            "reviewer": operator, "comment": comment,
            "label": label_written, "label_source": "人工标注" if label_written is not None else "",
            "allowed_transitions": allowed_transitions(target_status)}


# ====================================================================== 超时自动关闭
def auto_close_timeout_cases(db: Any, hours: Optional[int] = None,
                             operator: str = "system",
                             dry_run: bool = False) -> Dict[str, Any]:
    """宝典 9.4 关键代码 3：24h 没人审 → 系统自动关闭 + 写审计（operator=system）。

    `dry_run=True` 只列出将被关闭的案件，不真正改状态（前端"预览"按钮用）。
    """
    hours = settings.CASE_TIMEOUT_HOURS if hours is None else hours
    if hours <= 0:
        return {"closed": 0, "hours": hours, "enabled": False, "dry_run": dry_run,
                "case_ids": [], "message": "CASE_TIMEOUT_HOURS = 0，自动关闭功能已停用"}

    threshold = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    cases = db.fetch_all(
        "SELECT case_id, case_status, create_time FROM risk_case "
        "WHERE case_status = '待审核' AND create_time < ? AND deleted_at IS NULL", [threshold])
    comment = f"系统自动关闭: 超过 {hours} 小时未处理"

    if dry_run:
        return {"closed": 0, "would_close": len(cases), "hours": hours, "enabled": True,
                "dry_run": True, "threshold": threshold,
                "case_ids": [c["case_id"] for c in cases]}

    for case in cases:
        db.update("risk_case", {"case_status": "已关闭", "reviewer": operator,
                                "review_comment": comment, "review_time": _now(),
                                "update_time": _now()},
                  "case_id = ?", [case["case_id"]])
        record_action(db, operator=operator, action_type="案件流转:待审核→已关闭",
                      target_type="案件", target_id=case["case_id"],
                      before_value={"case_status": "待审核"},
                      after_value={"case_status": "已关闭"}, remark=comment)
    db.commit()
    logger.info("超时自动关闭案件 %d 个（阈值 %d 小时）", len(cases), hours)
    return {"closed": len(cases), "would_close": len(cases), "hours": hours, "enabled": True,
            "dry_run": False, "threshold": threshold,
            "case_ids": [c["case_id"] for c in cases]}


def case_stats(db: Any) -> Dict[str, Any]:
    rows = db.fetch_all(
        "SELECT case_status, COUNT(*) AS cnt FROM risk_case WHERE deleted_at IS NULL "
        "GROUP BY case_status")
    summary = {status: 0 for status in _ALLOWED_CASE_TRANSITIONS}
    for row in rows:
        summary[row["case_status"]] = row["cnt"]
    pending = summary.get("待审核", 0)
    return {"summary": summary, "pending": pending,
            "active": pending + summary.get("审核中", 0),
            "total": sum(summary.values())}
