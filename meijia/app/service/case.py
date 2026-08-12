"""案件维护服务: 超时自动关闭 (调度器调用)。

Commit 策略: 函数内自提交, 调用方不需要再 commit。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models_risk import RiskCase
from app.service.action_log import record_action

logger = logging.getLogger(__name__)


def auto_close_timeout_cases(db: Session, *, operator: str = "system") -> int:
    """把超过 CASE_TIMEOUT_HOURS 仍未审核的"待审核"案件自动关闭。

    返回关闭数量。0 = 功能关闭 (CASE_TIMEOUT_HOURS=0)。
    """
    if settings.CASE_TIMEOUT_HOURS <= 0:
        return 0
    cutoff = datetime.now() - timedelta(hours=settings.CASE_TIMEOUT_HOURS)
    rows = list(db.scalars(select(RiskCase).where(
        RiskCase.case_status == "待审核",
        RiskCase.created_at < cutoff,
    )))
    for case in rows:
        before = {"case_status": case.case_status}
        case.case_status = "已关闭"
        case.reviewer = operator
        case.review_comment = f"超过 {settings.CASE_TIMEOUT_HOURS} 小时未审核, 系统自动关闭"
        case.reviewed_at = datetime.now()
        record_action(
            db, operator=operator, action_type="AUTO_CLOSE_CASE", target_type="case",
            target_id=case.case_id, before_value=before,
            after_value={"case_status": "已关闭", "review_comment": case.review_comment},
            remark=f"timeout={settings.CASE_TIMEOUT_HOURS}h",
        )
    if rows:
        db.commit()
        logger.info("auto_close_timeout_cases: 关闭 %d 个超时案件", len(rows))
    return len(rows)
