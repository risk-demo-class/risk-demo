"""
事件处理管道 (教育版): process_event 统一入口

4 步业务流:
  1. 业务实体校验 (用户/订单/退费等是否存在)
  2. 自动补全关联业务参数 (course_id, device_id)
  3. 黑名单前置拦截 (用户/学号/身份证/设备指纹/支付账号/手机号 6 级短路)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import Complaint, LearningProgress, OrderInfo, RefundRequest, StudentProfile, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 course_id / device_id (黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查 (6 级短路)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 学号 > 身份证 > 设备指纹 > 支付账号 > 手机号; 短路返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    # 1. 用户黑名单 (必查)
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 学号黑名单 (通过 event_data 传 student_id)
    if request.event_data and request.event_data.get("student_id") is not None:
        if await check_blacklist(db, "学号", str(request.event_data["student_id"])):
            return "学号"

    # 3. 身份证黑名单 (从 StudentProfile 查)
    if request.user_id:
        row = (await db.execute(
            select(StudentProfile.id_card_hash).where(
                StudentProfile.user_id == request.user_id
            ).limit(1)
        )).first()
        if row and row.id_card_hash and await check_blacklist(db, "身份证", row.id_card_hash):
            return "身份证"

    # 4. 设备指纹黑名单
    if request.device_id:
        if await check_blacklist(db, "设备指纹", request.device_id):
            return "设备指纹"

    # 5. 支付账号黑名单 (purchase 事件)
    if request.event_type == "purchase" and request.order_id:
        row = (await db.execute(
            select(OrderInfo.amount).where(OrderInfo.order_id == request.order_id).limit(1)
        )).first()
        if row and await check_blacklist(db, "支付账号", str(row.amount)):
            return "支付账号"

    # 6. 手机号黑名单 (从 UserInfo 查)
    row = (await db.execute(
        select(UserInfo.phone).where(UserInfo.user_id == request.user_id).limit(1)
    )).first()
    if row and row.phone and await check_blacklist(db, "手机号", row.phone):
        return "手机号"

    return None


# 按 event_type 自动补全业务字段
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type == "purchase":
        if not request.order_id:
            request.order_id = request.source_id
        if request.order_id:
            row = (await db.execute(
                select(OrderInfo.course_id, OrderInfo.amount)
                .where(OrderInfo.order_id == request.order_id)
            )).first()
            if row:
                request.course_id = request.course_id or row.course_id
                request.event_data = request.event_data or {}
                request.event_data["amount"] = float(row.amount)

    elif request.event_type == "course_watch":
        if not request.order_id:
            request.order_id = request.source_id
        # 从学习进度信息注入 event_data
        row = (await db.execute(
            select(LearningProgress.total_minutes, LearningProgress.completion_rate)
            .where(LearningProgress.user_id == request.user_id)
            .order_by(LearningProgress.last_active_at.desc())
            .limit(1)
        )).first()
        if row:
            request.event_data = request.event_data or {}
            request.event_data["study_minutes"] = row.total_minutes
            request.event_data["completion_rate"] = float(row.completion_rate)

    elif request.event_type == "refund_apply":
        row = (await db.execute(
            select(RefundRequest.order_id, RefundRequest.study_minutes_before_refund,
                   RefundRequest.refund_amount)
            .where(RefundRequest.refund_id == request.source_id)
        )).first()
        if row:
            request.order_id = request.order_id or row.order_id
            request.event_data = request.event_data or {}
            request.event_data["study_minutes_before_refund"] = row.study_minutes_before_refund
            request.event_data["refund_amount"] = float(row.refund_amount)

    elif request.event_type == "complaint":
        row = (await db.execute(
            select(Complaint.course_id, Complaint.complaint_type)
            .where(Complaint.complaint_id == request.source_id)
        )).first()
        if row:
            request.course_id = request.course_id or row.course_id
            request.event_data = request.event_data or {}
            request.event_data["complaint_type"] = row.complaint_type

    # register / login / real_name_auth / coupon_claim 通常不需要补全
    return request


# 黑名单拒绝响应 (不走 7 步引擎)
def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
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