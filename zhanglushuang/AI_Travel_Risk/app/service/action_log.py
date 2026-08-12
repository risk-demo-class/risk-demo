"""
风控操作审计日志服务.

规则 / 案件 / 黑名单 / 模型相关变更都写一条日志, 保证可追溯.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskActionLog

logger = logging.getLogger(__name__)


async def record_action(
    db: AsyncSession,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before_value: Optional[dict] = None,
    after_value: Optional[dict] = None,
    ip: Optional[str] = None,
    remark: Optional[str] = None,
) -> RiskActionLog:
    """写入一条操作审计日志, 不 commit, 由调用方统一控制事务."""
    try:
        log = RiskActionLog(
            operator=operator or "system",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_value=before_value,
            after_value=after_value,
            ip=ip,
            remark=remark,
        )
        db.add(log)
        logger.info(
            "审计日志: operator=%s action=%s target=%s:%s",
            operator,
            action_type,
            target_type,
            target_id,
        )
        return log
    except Exception:
        logger.exception("写入审计日志失败: action=%s target=%s:%s", action_type, target_type, target_id)
        raise
