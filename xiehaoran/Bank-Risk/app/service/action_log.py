"""操作审计日志服务: 任何规则/案件/黑名单变更都写一行, 出事能追责."""
import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models_risk import RiskActionLog

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
) -> None:
    try:
        db.add(RiskActionLog(
            operator=operator,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_value=json.dumps(before_value, ensure_ascii=False) if before_value is not None else None,
            after_value=json.dumps(after_value, ensure_ascii=False) if after_value is not None else None,
            ip=ip,
            remark=remark,
        ))
    except Exception as e:
        logger.warning("记录审计日志失败: %s", e)
