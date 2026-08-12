"""
教育风控事件处理管道（``process_event`` 统一入口）。

核心流程保持不变：业务校验 -> 黑名单前置拦截 -> ``run_risk_check``。
"""
import logging
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import BlacklistExtra, RiskBlacklist, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """教育风控唯一业务入口。"""
    await validate_risk_check_request(db, request)

    blocked_by = await _check_all_blacklists(db, request.user_id)
    if blocked_by is not None:
        logger.warning("教育黑名单拦截: type=%s user_id=%s", blocked_by, request.user_id)
        return _blacklist_reject(request, blocked_by)

    return await run_risk_check(db, request)


async def _check_core_blacklist(db: AsyncSession, type_name: str, value: str | None) -> bool:
    if not value:
        return False
    now = datetime.now()
    found = (
        await db.execute(
            select(RiskBlacklist.blacklist_id).where(
                RiskBlacklist.blacklist_type == type_name,
                RiskBlacklist.blacklist_value == value,
                RiskBlacklist.deleted_at.is_(None),
                or_(RiskBlacklist.expire_time.is_(None), RiskBlacklist.expire_time > now),
            ).limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def _check_extra_blacklist(db: AsyncSession, type_name: str, value: str | None) -> bool:
    if not value:
        return False
    now = datetime.now()
    found = (
        await db.execute(
            select(BlacklistExtra.entry_id).where(
                BlacklistExtra.type == type_name,
                BlacklistExtra.value == value,
                BlacklistExtra.status == "ACTIVE",
                or_(BlacklistExtra.expire_at.is_(None), BlacklistExtra.expire_at > now),
            ).limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def _check_all_blacklists(db: AsyncSession, user_id: str) -> str | None:
    """优先级：用户 -> 学号 -> 身份证 -> 设备，一旦命中立即短路。"""
    user = (
        await db.execute(select(UserInfo).where(UserInfo.user_id == user_id).limit(1))
    ).scalar_one()

    if await _check_core_blacklist(db, "用户", user.user_id):
        return "用户"
    checks = (
        ("学号", "student_id", user.student_id),
        ("身份证", "id_card", user.id_card_hash),
        ("设备", "device_id", user.device_id),
    )
    for display_name, extra_type, value in checks:
        if await _check_core_blacklist(db, display_name, value):
            return display_name
        if await _check_extra_blacklist(db, extra_type, value):
            return display_name
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """黑名单是系统保护动作：保持原项目语义，不写评估和案件表。"""
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="拒绝",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        blocked_by=blocked_by,
    )
