# -*- coding: utf-8 -*-
"""审计服务 —— 对应教学宝典 Anki 25「审计怎么记？record_action(db, operator, action_type, before/after)」

所有**改变系统状态**的动作都要留痕：
    案件流转 / 规则增删改 / 黑名单增删 / 模型训练 / 超时自动关闭（operator=system）
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_risk.service.action_log")


def _dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def record_action(db: Any, operator: str, action_type: str, target_type: str = "",
                  target_id: str = "", before_value: Any = None, after_value: Any = None,
                  remark: str = "") -> int:
    """写一条审计日志（不单独 commit，跟随调用方事务）。"""
    log_id = db.insert("risk_action_log", {
        "operator": operator or "unknown",
        "action_type": action_type,
        "target_type": target_type,
        "target_id": str(target_id),
        "before_value": _dump(before_value),
        "after_value": _dump(after_value),
        "remark": remark,
    })
    logger.info("审计: operator=%s action=%s target=%s/%s", operator, action_type, target_type, target_id)
    return log_id


def query_actions(db: Any, target_type: str = "", target_id: str = "", operator: str = "",
                  action_type: str = "", limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    where: List[str] = ["1=1"]
    params: List[Any] = []
    if target_type:
        where.append("target_type = ?")
        params.append(target_type)
    if target_id:
        where.append("target_id = ?")
        params.append(str(target_id))
    if operator:
        where.append("operator = ?")
        params.append(operator)
    if action_type:
        where.append("action_type LIKE ?")
        params.append(f"%{action_type}%")
    clause = " AND ".join(where)
    total = db.scalar(f"SELECT COUNT(*) FROM risk_action_log WHERE {clause}", params)
    rows = db.fetch_all(
        f"SELECT * FROM risk_action_log WHERE {clause} ORDER BY log_id DESC LIMIT ? OFFSET ?",
        params + [limit, offset])
    return {"total": total, "items": rows, "limit": limit, "offset": offset}
