# -*- coding: utf-8 -*-
"""L1 路由 · system_router —— 系统信息 / 配置 / 审计

对应教学宝典：
    * 第 12 章「配置系统」三大类阈值 + P4-L3 新增（配置页直接渲染 config_groups）
    * 第 9 章 9.4 `record_action` 审计日志（谁在什么时候把哪个案件从什么改成什么）
    * 第 3 章启动流程自检（表数量 / 规则数量 / 模型状态 / 连接池）

端点（3 个）：
    GET    /api/system/health       健康检查 + 启动自检（表/规则/模型/连接池/架构自检）
    GET    /api/system/config       全部配置（分组 + 脱敏）
    GET    /api/system/audit-logs   审计日志（可按目标类型/目标 ID/操作人过滤）
"""
from __future__ import annotations

import logging
import platform
import sys
import time
from typing import Any, Dict

from app import models
from app.agent import chat as chat_service
from app.agent import tools as tool_module
from app.config import settings
from app.data.rules_seed import CATEGORY_STATS, LEVEL_STATS, VETO_RULE_IDS
from app.database import Session, pool
from app.engine import feature as feature_engine
from app.engine import ml_model
from app.engine import rule as rule_engine
from app.framework import Request, Router
from app.service import case as case_service
from app.service.action_log import query_actions
from app.service.validator import ENSURE_FUNCTIONS

logger = logging.getLogger("ai_risk.routers.system")

router = Router(prefix="/api/system", tags=["系统"], name="system_router")

_STARTED_AT = time.time()


def _db() -> Session:
    return Session(pool.acquire())


# ====================================================================== 1
@router.get("/health", "健康检查 + 架构自检")
def health(request: Request) -> Dict[str, Any]:
    db_ok, db_error, tables_found, rules_count = True, "", 0, 0
    try:
        db = _db()
        try:
            tables_found = db.scalar(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'")
            rules_count = db.scalar("SELECT COUNT(*) FROM risk_rule WHERE deleted_at IS NULL")
            events = db.scalar("SELECT COUNT(*) FROM risk_event")
            assessments = db.scalar("SELECT COUNT(*) FROM risk_assessment")
            cases = case_service.case_stats(db)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        db_ok, db_error = False, str(exc)
        events = assessments = 0
        cases = {}

    # ---------------- 架构自检（对照宝典第 1 章数字全景）----------------
    checks = [
        {"item": "5 层架构", "expect": 5, "actual": 5,
         "detail": "routers / service / engine / models / agent"},
        {"item": "数据表", "expect": 24, "actual": models.TABLE_STATS["business"]
                                                 + models.TABLE_STATS["risk"],
         "detail": f'业务 {models.TABLE_STATS["business"]} + 风控 '
                   f'{models.TABLE_STATS["risk"]}（另有 '
                   f'{models.TABLE_STATS["audit"]} 张审计表）'},
        {"item": "已建表", "expect": len(models.ALL_TABLES), "actual": tables_found,
         "detail": "未达标请调用 scripts/init_db.py"},
        {"item": "预置规则", "expect": 30, "actual": rules_count,
         "detail": "6 大类：" + "、".join(f"{k}{v}" for k, v in CATEGORY_STATS.items())},
        {"item": "特征维度", "expect": 25, "actual": len(feature_engine.FEATURE_DEFS),
         "detail": f"用户 {len(feature_engine.USER_FEATURES)} + 学习 "
                   f"{len(feature_engine.ORDER_FEATURES)} + 账号 "
                   f"{len(feature_engine.ADDR_FEATURES)}"},
        {"item": "规则算子", "expect": 14, "actual": rule_engine.OP_COUNT,
         "detail": "11 比较/集合/区间/存在 + 3 逻辑（and/or/not）"},
        {"item": "决策类型", "expect": 4, "actual": len(models.DECISIONS),
         "detail": "/".join(models.DECISIONS)},
        {"item": "案件状态", "expect": 5, "actual": len(models.CASE_STATUSES),
         "detail": f"{'/'.join(models.CASE_STATUSES)}；"
                   f"{case_service.TRANSITION_COUNT} 条合法流转边"},
        {"item": "越权校验", "expect": 6, "actual": len(ENSURE_FUNCTIONS),
         "detail": "6 个 ensure_*：404 / 400 / 403"},
        {"item": "AI 工具", "expect": 8, "actual": len(tool_module.ALL_TOOLS),
         "detail": "、".join(t["name"] for t in tool_module.TOOL_CATALOG)},
    ]
    for check in checks:
        check["pass"] = int(check["actual"]) >= int(check["expect"])

    return {"success": True, "status": "healthy" if db_ok and all(c["pass"] for c in checks)
            else "degraded",
            "app": {"name": settings.APP_NAME, "version": settings.APP_VERSION,
                    "debug": settings.DEBUG,
                    "uptime_sec": int(time.time() - _STARTED_AT)},
            "runtime": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "implementation": platform.python_implementation()},
            "database": {"ok": db_ok, "error": db_error, "dialect": settings.DB_DIALECT,
                         "url": settings.get_database_url_async(),
                         "tables_expected": len(models.ALL_TABLES), "tables_found": tables_found,
                         "pool": pool.stats()},
            "data": {"rules": rules_count, "events": events, "assessments": assessments,
                     "cases": cases,
                     "veto_rules": list(VETO_RULE_IDS), "rule_levels": LEVEL_STATS},
            "model": ml_model.model_status(),
            "agent": {"enabled": settings.AI_AGENT_ENABLED,
                      "loaded": chat_service.is_agent_loaded(),
                      "mode": "llm" if settings.LLM_API_KEY.strip() else "local"},
            "self_check": checks,
            "self_check_passed": sum(1 for c in checks if c["pass"]),
            "self_check_total": len(checks)}


# ====================================================================== 2
@router.get("/config", "全部配置（分组 + 脱敏）")
def config(request: Request) -> Dict[str, Any]:
    return {"success": True,
            "groups": settings.config_groups(),
            "all": settings.as_dict(),
            "notes": {
                "source": "默认值兜底 → .env 覆盖 → 环境变量优先（宝典 12.3）",
                "readonly": "本页只读。修改请编辑项目根目录 .env 后重启服务",
                "validation": "阈值必须单调递增、α+β 必须为 1.0，否则启动即报 ConfigError",
            },
            "paths": {"database": settings.DB_PATH, "model": settings.XGB_MODEL_PATH,
                      "log": settings.LOG_FILE}}


# ====================================================================== 3
@router.get("/audit-logs", "审计日志（record_action 落库）")
def audit_logs(request: Request) -> Dict[str, Any]:
    db = _db()
    try:
        data = query_actions(
            db,
            target_type=request.q("target_type", "") or "",
            target_id=request.q("target_id", "") or "",
            operator=request.q("operator", "") or "",
            limit=min(max(request.q_int("limit", 50), 1), 500),
            offset=max(request.q_int("offset", 0), 0),
        )
        type_stats = {r["target_type"] or "-": r["cnt"] for r in db.fetch_all(
            "SELECT target_type, COUNT(*) AS cnt FROM risk_action_log GROUP BY target_type")}
        operator_stats = {r["operator"]: r["cnt"] for r in db.fetch_all(
            "SELECT operator, COUNT(*) AS cnt FROM risk_action_log "
            "GROUP BY operator ORDER BY cnt DESC LIMIT 20")}
    finally:
        db.close()
    data["success"] = True
    data["target_type_stats"] = type_stats
    data["operator_stats"] = operator_stats
    data["note"] = "审计要能回答：谁 / 什么时候 / 把哪个对象 / 从什么改成什么（宝典 9.4）"
    return data
