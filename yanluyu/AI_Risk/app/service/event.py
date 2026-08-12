"""
教育风控事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (用户/订单/退费/打赏是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (course_id, device_fingerprint 等)
  3. 黑名单前置拦截 (用户/学号/身份证号 3 种类型, 撞黑就拒)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    BlacklistExtra,
    Course,
    DonationRecord,
    OrderInfo,
    RefundRequest,
    UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 course_id / device_fingerprint
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查: 用户 > 学号 > 身份证号 (> 设备指纹)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


# 优先级: 用户 > 学号 > 身份证号; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    # 1. 用户黑名单
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 2. 学号黑名单 (R030)
    row = (await db.execute(
        select(UserInfo.student_id).where(UserInfo.user_id == request.user_id)
    )).first()
    if row and row.student_id and await check_blacklist(db, "学号", row.student_id):
        return "学号"

    # 3. 身份证号黑名单 (R030)
    row2 = (await db.execute(
        select(UserInfo.id_number).where(UserInfo.user_id == request.user_id)
    )).first()
    if row2 and row2.id_number and await check_blacklist(db, "身份证号", row2.id_number):
        return "身份证号"

    return None


# 按 event_type 自动补全 course_id / device_fingerprint
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type == "报名":
        if request.order_id:
            row = (await db.execute(
                select(OrderInfo.course_id, OrderInfo.device_fingerprint)
                .where(OrderInfo.order_id == request.order_id)
            )).first()
            if row:
                if not request.course_id:
                    request.course_id = row.course_id

    elif request.event_type == "退费申请":
        # source_id 是 refund_id, 查 order_id 和 course_id
        if not request.order_id:
            row = (await db.execute(
                select(RefundRequest.order_id).where(RefundRequest.refund_id == request.source_id)
            )).first()
            if row:
                request.order_id = row.order_id

    elif request.event_type == "打赏":
        # source_id 是 donation_id
        if not request.donation_id:
            request.donation_id = request.source_id

    return request


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
