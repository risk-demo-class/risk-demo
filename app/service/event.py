"""教育风控事件入口：校验 → 黑名单 → 复用 7 步风控流水线。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import Enrollment, RefundRequest, UserInfo
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    request = await _enrich_request(db, request)
    if await check_blacklist(db, "用户", request.user_id):
        return _blacklist_reject(request, "用户")
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == request.user_id))).scalar_one()
    if user.student_id and await check_blacklist(db, "学号", user.student_id):
        return _blacklist_reject(request, "学号")
    if user.device_id and await check_blacklist(db, "设备指纹", user.device_id):
        return _blacklist_reject(request, "设备指纹")
    return await run_risk_check(db, request)


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type == "课程报名":
        request.order_id = request.source_id
    elif request.event_type == "退费申请":
        enrollment_id = (await db.execute(select(RefundRequest.enrollment_id).where(RefundRequest.refund_id == request.source_id))).scalar_one()
        request.order_id = enrollment_id
    return request


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject", event_id="blacklist_reject", user_id=request.user_id,
        final_score=100, risk_level="极高", decision="拒绝", rule_count=0,
        triggered_rules=[], features={}, create_time=datetime.now(), blocked_by=blocked_by,
    )
