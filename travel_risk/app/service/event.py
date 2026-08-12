"""
事件处理管道 (process_event 统一入口)

5 步业务流:
  0. 入参解析: 用户ID / 业务ID / 设备ID 任一即可, 缺的自动补全
  1. 业务实体校验 (有业务ID时校验存在与归属)
  2. 自动补全关联业务参数 (booking_id / contact_phone)
  3. 黑名单前置拦截 (用户/手机号/设备 3 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    BookingInfo,
    ClaimInfo,
    ComplaintInfo,
    PaymentInfo,
    RefundChange,
    UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 0. 入参解析: 补全 user_id / event_type / source_id
    request = await _resolve_request(db, request)

    # 1. 业务实体校验 (有业务ID且事件类型明确时才校验)
    await validate_risk_check_request(db, request)

    # 2. 补全 booking_id / contact_phone / device (黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查 (用户 > 手机号 > 设备, 短路)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步
    return await run_risk_check(db, request)


async def _resolve_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """入参解析: 用户ID / 业务ID / 设备ID 至少提供一个, 缺失维度自动补全."""
    if not (request.user_id or request.source_id or request.device_id):
        raise HTTPException(status_code=400, detail="请至少提供 用户ID / 业务ID / 设备ID 中的一个")

    # 1. 有业务ID但没有用户ID → 从业务表反查用户 + 推断事件类型
    if request.source_id and not request.user_id:
        resolved = await _resolve_user_from_source(db, request.source_id, request.event_type)
        if resolved:
            request.user_id = resolved[0]
            if not request.event_type:
                request.event_type = resolved[1]
        elif request.device_id:
            # source_id 无法识别时, 交给设备维度继续解析
            pass
        else:
            # 既不是已知业务ID也不是设备 → 尝试当作用户ID (注册检查)
            if await _user_exists(db, request.source_id):
                request.user_id = request.source_id
                request.event_type = request.event_type or "注册"
            else:
                raise HTTPException(status_code=404, detail=f"业务ID无法解析: {request.source_id}")

    # 2. 有设备ID但没有用户ID → 反查最近绑定用户
    if request.device_id and not request.user_id:
        user_id = await _resolve_user_from_device(db, request.device_id)
        if not user_id:
            raise HTTPException(status_code=404, detail=f"设备未绑定任何用户: {request.device_id}")
        request.user_id = user_id
        request.event_type = request.event_type or "通用"

    # 3. 默认事件类型: 只给用户ID/设备ID时走"通用" (账户级规则)
    if not request.event_type:
        request.event_type = "通用"

    # 4. source_id 兜底: 用户级/设备级检查用 user_id / device_id 充当业务ID
    if not request.source_id:
        request.source_id = request.device_id or request.user_id

    return request


async def _resolve_user_from_source(
    db: AsyncSession,
    source_id: str,
    event_type: str | None,
) -> tuple[str, str] | None:
    """业务ID → (user_id, event_type). event_type 已知时只查对应表, 未知时按顺序探测."""
    probes = [
        ("下单", select(BookingInfo.user_id).where(BookingInfo.booking_id == source_id)),
        ("支付", select(PaymentInfo.user_id).where(PaymentInfo.payment_id == source_id)),
        ("退改申请", select(BookingInfo.user_id).select_from(RefundChange)
          .join(BookingInfo, RefundChange.booking_id == BookingInfo.booking_id)
          .where(RefundChange.refund_id == source_id)),
        ("理赔申请", select(ClaimInfo.user_id).where(ClaimInfo.claim_id == source_id)),
        ("投诉", select(ComplaintInfo.user_id).where(ComplaintInfo.complaint_id == source_id)),
        ("注册", select(UserInfo.user_id).where(UserInfo.user_id == source_id)),
    ]
    if event_type and event_type != "通用":
        probes = [p for p in probes if p[0] == event_type]
    for et, stmt in probes:
        row = (await db.execute(stmt)).first()
        if row:
            return row[0], et
    return None


async def _resolve_user_from_device(db: AsyncSession, device_id: str) -> str | None:
    """设备ID → 最近绑定该设备的用户."""
    from app.models import UserDevice
    row = (await db.execute(
        select(UserDevice.user_id).where(UserDevice.device_id == device_id)
        .order_by(UserDevice.bind_time.desc()).limit(1)
    )).first()
    return row[0] if row else None


async def _user_exists(db: AsyncSession, user_id: str) -> bool:
    row = (await db.execute(
        select(UserInfo.user_id).where(UserInfo.user_id == user_id)
    )).first()
    return row is not None


async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    """优先级: 用户 > 手机号 > 设备; 短路: 一旦撞黑立刻返回."""
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    phone = None
    if request.event_type in ("注册", "通用"):
        row = (await db.execute(
            select(UserInfo.phone).where(UserInfo.user_id == request.user_id)
        )).first()
        if row:
            phone = row.phone
    elif request.booking_id:
        row = (await db.execute(
            select(BookingInfo.contact_phone).where(BookingInfo.booking_id == request.booking_id)
        )).first()
        if row:
            phone = row.contact_phone
    if phone and await check_blacklist(db, "手机号", phone):
        return "手机号"

    if request.device_id and await check_blacklist(db, "设备", request.device_id):
        return "设备"

    return None


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """按 event_type 自动补全 booking_id."""
    if request.event_type == "注册":
        request.booking_id = None
        return request

    if request.event_type == "下单":
        if not request.booking_id:
            request.booking_id = request.source_id
        return request

    if request.event_type == "支付":
        if not request.booking_id:
            row = (await db.execute(
                select(PaymentInfo.booking_id).where(PaymentInfo.payment_id == request.source_id)
            )).first()
            if row:
                request.booking_id = row.booking_id
        return request

    if request.event_type == "退改申请":
        if not request.booking_id:
            row = (await db.execute(
                select(RefundChange.booking_id).where(RefundChange.refund_id == request.source_id)
            )).first()
            if row:
                request.booking_id = row.booking_id
        return request

    if request.event_type == "理赔申请":
        if not request.booking_id:
            row = (await db.execute(
                select(ClaimInfo.booking_id).where(ClaimInfo.claim_id == request.source_id)
            )).first()
            if row:
                request.booking_id = row.booking_id
        return request

    if request.event_type == "投诉":
        if not request.booking_id:
            row = (await db.execute(
                select(ComplaintInfo.booking_id).where(ComplaintInfo.complaint_id == request.source_id)
            )).first()
            if row:
                request.booking_id = row.booking_id
        return request

    return request


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """故意不写库: 黑名单拦截不算一次风控评估."""
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
        message=f"撞黑名单: {blocked_by}",
        blocked_by=blocked_by,
    )
