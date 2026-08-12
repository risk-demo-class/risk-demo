"""
操作审计日志.
任何规则/案件/黑名单的变更都调 record_action() 写一行.
合规要求: 银保监规定金融机构所有风控操作必须可追溯.

注意: 函数不 commit, 跟调用方合并成 1 个事务.
"""
import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.models import RiskActionLog

logger = logging.getLogger(__name__)


async def record_action(
    db: AsyncSession,
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
    """写 1 行操作审计日志 (不 commit, 由调用方 commit).

    Args:
        operator:     操作人 (admin / system / 用户ID)
        action_type:  CREATE_RULE / UPDATE_RULE / TOGGLE_RULE / DELETE_RULE /
                      REVIEW_CASE / AUTO_REJECT_CASE / AUTO_CLOSE_CASE /
                      ADD_BLACKLIST / REMOVE_BLACKLIST
        target_type:  rule / case / blacklist
        target_id:    操作对象的 ID
        before_value: 变更前值 (dict, 序列化为 JSON)
        after_value:  变更后值 (dict, 序列化为 JSON)
        ip:           操作 IP
        remark:       备注
    """
    log = RiskActionLog(
        operator=operator,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        # JSON 字符串存库, ensure_ascii=False 保留中文
        before_value=json.dumps(before_value, ensure_ascii=False) if before_value else None,
        after_value=json.dumps(after_value, ensure_ascii=False) if after_value else None,
        ip=ip,
        remark=remark,
    )
    db.add(log)
    logger.info(
        "action_log: %s by %s on %s(%s)",
        action_type, operator, target_type, target_id,
    )


def orm_to_dict(obj: Any, fields: list[str]) -> dict:
    """ORM 对象 → dict (只取 fields 指定字段).

    比 obj.__dict__ 安全: 不会暴露 SQLAlchemy 内部状态 (_sa_instance_state 等).
    """
    return {f: getattr(obj, f, None) for f in fields}
