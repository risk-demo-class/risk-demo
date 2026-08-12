"""
操作审计日志: 规则/案件/黑名单变更统一留痕 (合规追责)
"""
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskActionLog

logger = logging.getLogger(__name__)


async def record_action(
    db: AsyncSession,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before_value: dict | None = None,
    after_value: dict | None = None,
    ip: str | None = None,
    remark: str | None = None,
) -> None:
    """写一条操作审计日志."""
    log = RiskActionLog(
        operator=operator,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        before_value=json.dumps(before_value, ensure_ascii=False) if before_value is not None else None,
        after_value=json.dumps(after_value, ensure_ascii=False) if after_value is not None else None,
        ip=ip,
        remark=remark,
    )
    db.add(log)
    logger.info("审计日志: %s %s %s:%s", operator, action_type, target_type, target_id)
