# -*- coding: utf-8 -*-
"""L1 路由 · case_router —— 案件工作台（可疑旅客调查档案）

对应教学宝典第 9 章「案件状态机」：
    * 5 状态 · 白名单流转（非法流转 400）
    * 流转必须带 operator，全部落审计日志
    * 人工结论回写 `risk_assessment.label`（人工标注 → 模型训练标签）
    * 超时自动关闭（CASE_TIMEOUT_HOURS，operator=system）

端点（4 个）：
    GET    /api/cases                      案件列表（默认只看活跃态，含状态机文档）
    GET    /api/cases/{case_id}            案件详情（评估 + 特征 + 操作轨迹）
    PUT    /api/cases/{case_id}/status     状态流转（白名单校验）
    POST   /api/cases/auto-close           超时案件批量自动关闭
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.database import Session, pool
from app.framework import HTTPError, Request, Router
from app.models import CASE_STATUSES, RISK_LEVELS
from app.service import case as case_service

logger = logging.getLogger("ai_risk.routers.case")

router = Router(prefix="/api/cases", tags=["案件工作台"], name="case_router")


def _db() -> Session:
    return Session(pool.acquire())


# ====================================================================== 1
@router.get("", "案件列表（默认只看待审核/审核中）")
def list_cases(request: Request) -> Dict[str, Any]:
    db = _db()
    try:
        data = case_service.list_cases(
            db,
            active_only=request.q_bool("active_only", True),
            case_status=request.q("case_status", "") or "",
            user_id=request.q("user_id", "") or "",
            risk_level=request.q("risk_level", "") or "",
            keyword=request.q("keyword", "") or "",
            limit=min(max(request.q_int("limit", 20), 1), 200),
            offset=max(request.q_int("offset", 0), 0),
        )
        data["stats"] = case_service.case_stats(db)
    finally:
        db.close()
    data["success"] = True
    data["meta"] = {
        "state_machine": case_service.state_machine_doc(),
        "statuses": list(CASE_STATUSES),
        "risk_levels": list(RISK_LEVELS),
    }
    return data


# ====================================================================== 2
@router.get("/{case_id}", "案件详情（含可流转目标态）")
def case_detail(request: Request) -> Dict[str, Any]:
    case_id = request.path_params["case_id"]
    db = _db()
    try:
        detail = case_service.get_case(db, case_id)
    finally:
        db.close()
    if not detail:
        raise HTTPError(404, f"案件不存在: {case_id}")
    return {"success": True, "data": detail,
            "meta": {"state_machine": case_service.state_machine_doc()}}


# ====================================================================== 3
@router.put("/{case_id}/status", "案件状态流转（白名单校验 + 审计）")
def transition(request: Request) -> Dict[str, Any]:
    case_id = request.path_params["case_id"]
    payload = request.json()
    target = str(payload.get("case_status") or payload.get("target_status") or "").strip()
    operator = str(payload.get("operator") or request.headers.get("x-operator", "") or "").strip()
    if not target:
        raise HTTPError(400, "case_status（目标状态）必填")
    if not operator:
        # 宝典 9.3：流转必须带 operator，否则审计断链
        raise HTTPError(400, "operator（操作人）必填 —— 审计要求可追溯")

    db = _db()
    try:
        result = case_service.transition_case(
            db, case_id, target, operator,
            comment=str(payload.get("review_comment") or payload.get("comment") or ""),
            label=payload.get("label"),
        )
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("案件流转失败: %s", exc)
        raise HTTPError(500, f"案件流转失败: {exc}") from exc
    finally:
        db.close()
    logger.info("案件 %s 流转 → %s by %s", case_id, target, operator)
    return {"success": True, "data": result}


# ====================================================================== 4
@router.post("/auto-close", "超时案件批量自动关闭（operator=system）")
def auto_close(request: Request) -> Dict[str, Any]:
    payload = request.json() if request.body else {}
    hours = payload.get("hours")
    db = _db()
    try:
        result = case_service.auto_close_timeout_cases(
            db, hours=int(hours) if hours not in (None, "") else None,
            dry_run=bool(payload.get("dry_run", False)))
        db.commit()
    except HTTPError:
        db.rollback()
        raise
    finally:
        db.close()
    return {"success": True, "data": result}
