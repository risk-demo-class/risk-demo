"""教育事件处理统一入口。

处理顺序：业务实体校验 → 解析事件上下文 → 四类黑名单短路 → 七步决策流水线。
黑名单命中不写 risk_event/risk_assessment，避免把系统保护动作混入模型样本。
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.engine.feature import EducationEventContext, resolve_event_context
from app.models import UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """教育风控的唯一事件入口。"""
    await validate_risk_check_request(db, request)
    event_context = await resolve_event_context(
        db,
        event_type=request.event_type,
        source_id=request.source_id,
        user_id=request.user_id,
    )

    blocked_by = await _check_all_blacklists(db, request, event_context)
    if blocked_by is not None:
        logger.warning(
            "教育事件命中黑名单: type=%s user_id=%s event_type=%s source_id=%s",
            blocked_by,
            request.user_id,
            request.event_type,
            request.source_id,
        )
        return _blacklist_reject(request, blocked_by)

    return await run_risk_check(db, request, event_context=event_context)


async def _blacklist_candidates(
    db: AsyncSession,
    request: RiskCheckRequest,
    event_context: EducationEventContext,
) -> list[tuple[str, str]]:
    """按用户 → 学号 → 身份证 → 设备指纹的顺序生成待检查值。"""
    identity = (
        await db.execute(
            select(UserInfo.student_id_hash, UserInfo.id_number_hash).where(
                UserInfo.user_id == request.user_id
            )
        )
    ).first()
    candidates: list[tuple[str, str]] = [("用户", request.user_id)]
    if identity and identity.student_id_hash:
        candidates.append(("学号", identity.student_id_hash))
    if identity and identity.id_number_hash:
        candidates.append(("身份证", identity.id_number_hash))
    if event_context.device_id_hash:
        candidates.append(("设备指纹", event_context.device_id_hash))
    return candidates


async def _check_all_blacklists(
    db: AsyncSession,
    request: RiskCheckRequest,
    event_context: EducationEventContext,
) -> str | None:
    """顺序短路检查四类黑名单，返回首先命中的逻辑类型。"""
    for blacklist_type, value in await _blacklist_candidates(db, request, event_context):
        if await check_blacklist(db, blacklist_type, value):
            return blacklist_type
    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """构造黑名单直接拒绝响应，不制造普通评估记录。"""
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
        ml_score=None,
        ml_decision=None,
        blocked_by=blocked_by,
    )


if __name__ == "__main__":
    print("教育事件流程：实体校验 → 用户/学号/身份证/设备黑名单 → 25维特征 → 规则/模型 → 决策")
