"""教育风控事件入口；保持“校验、补全、黑名单、决策”四步顺序。"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LearningProgress, LiveReward, OrderInfo, RefundRequest, UserInfo
from app.education_compat import to_core_event, to_education_category
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def run_risk_check(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """延迟加载决策引擎，使阶段 8 改造特征前事件模块也能独立校验。"""
    from app.engine.decision import run_risk_check as decision_run_risk_check

    return await decision_run_risk_check(db, request)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全订单、设备和事件快照
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查（行业扩展黑名单在阶段 7 接入）
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("命中黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 调用原有 7 步决策流水线。老师的核心表枚举保持不变，因此在写库前
    # 将教育事件转换为等价核心枚举；教育名称保存在事件快照并在查询层还原。
    education_event_type = request.event_type
    event_data = dict(request.event_data or {})
    event_data["education_event_type"] = education_event_type
    core_request = request.model_copy(update={
        "event_type": to_core_event(education_event_type),
        "event_data": event_data,
    })
    response = await run_risk_check(db, core_request)
    for hit in response.triggered_rules:
        hit.rule_category = to_education_category(hit.rule_category)
    return response


async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest
) -> str | None:
    """按固定优先级检查用户及四类教育业务标识。"""
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    user = (await db.execute(
        select(UserInfo.student_id, UserInfo.id_card_hash, UserInfo.device_id).where(
            UserInfo.user_id == request.user_id
        )
    )).first()
    candidates = []
    if user:
        candidates.extend((
            ("学号", user.student_id),
            ("身份证哈希", user.id_card_hash),
            ("设备指纹", request.device_id or user.device_id),
        ))
    live_account = (request.event_data or {}).get("live_session_id")
    candidates.append(("直播账号", live_account))
    for blacklist_type, value in candidates:
        if value and await check_blacklist(db, blacklist_type, value):
            return blacklist_type
    return None


async def _user_device(db: AsyncSession, user_id: str) -> str | None:
    return (await db.execute(
        select(UserInfo.device_id).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()


async def _enrich_request(
    db: AsyncSession, request: RiskCheckRequest
) -> RiskCheckRequest:
    """按教育事件补全 order_id、device_id 及可审计的事件快照。"""
    event_data = dict(request.event_data or {})
    device_id = request.device_id or event_data.get("device_id")

    if request.event_type == "课程报名":
        request.order_id = request.order_id or request.source_id

    elif request.event_type == "退费申请":
        row = (await db.execute(
            select(RefundRequest.order_id).where(RefundRequest.refund_id == request.source_id)
        )).first()
        if row:
            event_data.setdefault("related_order_id", row.order_id)
        request.order_id = request.source_id

    elif request.event_type == "直播打赏":
        row = (await db.execute(
            select(LiveReward.device_id, LiveReward.live_session_id).where(
                LiveReward.reward_id == request.source_id
            )
        )).first()
        if row:
            device_id = device_id or row.device_id
            event_data.setdefault("live_session_id", row.live_session_id)
        request.order_id = request.source_id

    elif request.event_type == "学习行为":
        row = (await db.execute(
            select(LearningProgress.order_id, LearningProgress.device_id).where(
                LearningProgress.progress_id == request.source_id
            )
        )).first()
        if row:
            event_data.setdefault("related_order_id", row.order_id)
            device_id = device_id or row.device_id
        request.order_id = request.source_id

    if not device_id:
        device_id = await _user_device(db, request.user_id)

    request.device_id = device_id
    # 原决策引擎第三类特征仍读取 receive_id；阶段 8 会把其语义改为设备关联。
    request.receive_id = request.receive_id or device_id
    if device_id:
        event_data.setdefault("device_id", device_id)
    request.event_data = event_data
    return request


def _blacklist_reject(
    request: RiskCheckRequest, blocked_by: str
) -> RiskCheckResponse:
    """黑名单拒绝不写风险评估表，保持老师项目原有行为。"""
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
