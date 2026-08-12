# -*- coding: utf-8 -*-
"""L1 路由 · risk_router —— 风控检查主入口

对应教学宝典：
    * 第 4 章 7 步流水线（`POST /api/risk/check` 是唯一入口）
    * 附录 A：``app/routers/risk.py`` → ``service.event.process_event``

端点（3 个）：
    POST   /api/risk/check                        触发一次风控检查（7 步流水线）
    GET    /api/risk/assessments                  评估历史列表（分页 + 多维过滤）
    GET    /api/risk/assessments/{assessment_id}  评估详情（25 维特征 + 命中规则 + 案件）
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.database import Session, pool
from app.engine import feature as feature_engine
from app.framework import HTTPError, Request, Router
from app.service import event as event_service

logger = logging.getLogger("ai_risk.routers.risk")

router = Router(prefix="/api/risk", tags=["风控检查"], name="risk_router")


def _db() -> Session:
    return Session(pool.acquire())


# ====================================================================== 1
@router.post("/check", "触发风控检查（7 步流水线，单事务）")
def risk_check(request: Request) -> Dict[str, Any]:
    """宝典 4.1 的 7 步全景：

    校验 → 上下文 → 补全 → 落事件 → 25 维特征 → 快照 → 规则 → 双轨融合 → commit

    请求体：
        {"event_type": "考试", "user_id": "1001", "source_id": "ORD10010001",
         "amount": 1999.0, "client_ip": "...", "device_id": "..."}
    """
    payload = request.json()
    if not payload:
        raise HTTPError(400, "请求体不能为空，至少需要 event_type / user_id / source_id")
    operator = str(payload.pop("operator", "") or request.headers.get("x-operator", "") or "api")

    db = _db()
    try:
        result = event_service.process_event(db, payload, operator=operator)
    except HTTPError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("风控检查失败: %s", exc)
        raise HTTPError(500, f"风控检查失败: {exc}") from exc
    finally:
        db.close()

    logger.info("风控检查完成 user=%s decision=%s score=%s",
                result["user_id"], result["decision"], result["final_score"])
    return {"success": True, "data": result}


# ====================================================================== 2
@router.get("/assessments", "评估历史列表")
def list_assessments(request: Request) -> Dict[str, Any]:
    db = _db()
    try:
        data = event_service.list_assessments(
            db,
            user_id=request.q("user_id", "") or "",
            decision=request.q("decision", "") or "",
            risk_level=request.q("risk_level", "") or "",
            event_type=request.q("event_type", "") or "",
            keyword=request.q("keyword", "") or "",
            limit=min(max(request.q_int("limit", 20), 1), 200),
            offset=max(request.q_int("offset", 0), 0),
        )
    finally:
        db.close()
    data["success"] = True
    return data


# ====================================================================== 3
@router.get("/assessments/{assessment_id}", "评估详情（含 25 维特征快照）")
def assessment_detail(request: Request) -> Dict[str, Any]:
    assessment_id = request.path_params["assessment_id"]
    db = _db()
    try:
        detail = event_service.get_assessment_detail(db, assessment_id)
    finally:
        db.close()
    if detail is None:
        raise HTTPError(404, f"评估不存在: {assessment_id}")
    detail["feature_defs"] = feature_engine.FEATURE_DEFS
    return {"success": True, "data": detail}
