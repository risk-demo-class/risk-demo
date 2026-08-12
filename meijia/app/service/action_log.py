"""操作审计日志 (P4-L1): 规则/案件/黑名单的每次变更都调 record_action() 留痕。

设计:
  - record_action() 不 commit, 跟调用方合并成 1 个事务 (避免审计半成功)
  - orm_to_dict() 安全取 ORM 字段, 不暴露 SQLAlchemy 内部状态
  - 合规价值: 任何变更可追溯 (银保监对风控系统的审计要求)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models_risk import RiskActionLog

logger = logging.getLogger(__name__)


def record_action(
    db: Session,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    *,
    before_value: Optional[dict] = None,
    after_value: Optional[dict] = None,
    ip: Optional[str] = None,
    remark: Optional[str] = None,
) -> None:
    """写 1 行操作审计日志 (不 commit, 由调用方 commit)。

    action_type: CREATE_RULE / UPDATE_RULE / TOGGLE_RULE / DELETE_RULE /
                 REVIEW_CASE / AUTO_CLOSE_CASE / AUTO_REJECT_CASE /
                 ADD_BLACKLIST / REMOVE_BLACKLIST
    target_type: rule / case / blacklist
    """
    log = RiskActionLog(
        operator=operator,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        before_value=json.loads(json.dumps(before_value, ensure_ascii=False)) if before_value else None,
        after_value=json.loads(json.dumps(after_value, ensure_ascii=False)) if after_value else None,
        ip=ip,
        remark=remark,
    )
    db.add(log)
    logger.info("action_log: %s by %s on %s(%s)", action_type, operator, target_type, target_id)


def orm_to_dict(obj: Any, fields: list[str]) -> dict:
    """ORM 对象 → dict (只取 fields 指定字段), 比 __dict__ 安全。"""
    return {f: getattr(obj, f, None) for f in fields}
