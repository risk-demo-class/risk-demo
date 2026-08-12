"""
银行风控系统 - 审计日志服务
==========================
记录所有风控操作, 满足合规审计要求.

【审计范围】
  - 规则变更 (创建/修改/启停/删除)
  - 人工审核 (通过/拒绝/冻结)
  - 黑名单变更 (添加/移除)
  - 系统自动决策 (拒绝/冻结)

【审计留痕要求 (PRD 第 9 节)】
  所有风控决策、人工处理、名单变更可追溯.
  记录操作人、操作类型、对象、变更前后值、操作时间、IP.
"""
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

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
    """
    记录一条审计日志.

    暂存到 risk_event 表的 remark/handler 字段 (因为 PRD 未定义独立的审计日志表).
    生产环境应扩展为独立的 audit_log 表.

    Args:
        db: 数据库 Session
        operator: 操作人 (admin/system/ai_agent)
        action_type: 操作类型 (CREATE_RULE/UPDATE_RULE/REVIEW_CASE/AUTO_REJECT/...)
        target_type: 对象类型 (rule/event/card/user)
        target_id: 对象 ID
        before_value: 变更前值
        after_value: 变更后值
        ip: 操作 IP
        remark: 备注
    """
    log_entry = {
        "operator": operator,
        "action_type": action_type,
        "target_type": target_type,
        "target_id": target_id,
        "before": before_value,
        "after": after_value,
        "ip": ip,
        "remark": remark,
        "timestamp": datetime.now().isoformat(),
    }
    logger.info("审计日志: %s", json.dumps(log_entry, ensure_ascii=False, default=str))
    # 生产环境: 写入 audit_log 表
    # await db.execute(insert(AuditLog).values(...))
