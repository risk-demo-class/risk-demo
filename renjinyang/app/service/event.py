"""旅游风控事件入口。

业务入口负责旅游实体校验、上下文补全和黑名单前置保护；通过后仍调用
``decision.run_risk_check`` 原有七步流水线，不在服务层复制决策逻辑。
"""
import logging
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import BlacklistExtra, OrderInfo, UserInfo, VisaApplication
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


# 风控核心表枚举保持不变，因此只在进入七步审计链路前做内部兼容映射。
_CORE_EVENT_TYPE = {
    "机票预订": "下单",
    "酒店预订": "下单",
    "签证申请": "支付",
    "跟团游报名": "下单",
    "退改申请": "售后申请",
}


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """处理五类旅游事件并返回统一风控响应。"""
    # 1. 校验用户、来源实体及订单归属。
    await validate_risk_check_request(db, request)

    # 2. 补全订单与目的地上下文。
    enriched = await _enrich_request(db, request)

    # 3. 用户/手机号/签证号/设备指纹黑名单前置保护。
    blocked = await _check_all_blacklists(db, enriched)
    if blocked:
        logger.warning("旅游业务黑名单拦截: type=%s user_id=%s", blocked, enriched.user_id)
        return _blacklist_reject(enriched, blocked)

    # 4. 兼容不可修改的核心枚举，并保留原始旅游事件供审计回溯。
    original_type = enriched.event_type
    event_data = dict(enriched.event_data or {})
    event_data.setdefault("tourism_event_type", original_type)
    core_request = enriched.model_copy(update={
        "event_type": _CORE_EVENT_TYPE[original_type],
        "event_data": event_data,
    })
    return await run_risk_check(db, core_request)


async def _extra_blacklisted(db: AsyncSession, entry_type: str, value: str | None) -> bool:
    """查询未过期的旅游业务扩展黑名单。"""
    if not value:
        return False
    count = (await db.execute(select(BlacklistExtra.entry_id).where(
        BlacklistExtra.type == entry_type,
        BlacklistExtra.value == value,
        or_(BlacklistExtra.expire_at.is_(None), BlacklistExtra.expire_at > datetime.now()),
    ).limit(1))).scalar_one_or_none()
    return count is not None


async def _check_all_blacklists(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    """按用户、手机号、签证号、设备指纹顺序执行前置检查。

    护照号不在此处短路：它由 25 维特征和 R030 规则处理，确保命中可被
    ``risk_feature``/``risk_assessment`` 完整审计。
    """
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    phone = (await db.execute(select(UserInfo.phone).where(
        UserInfo.user_id == request.user_id
    ))).scalar_one_or_none()
    if phone and (
        await check_blacklist(db, "手机号", phone)
        or await _extra_blacklisted(db, "手机号", phone)
    ):
        return "手机号"

    if request.event_type == "签证申请" and await _extra_blacklisted(
        db, "签证号", request.source_id
    ):
        return "签证号"

    device = (request.event_data or {}).get("device_fingerprint")
    if await _extra_blacklisted(db, "设备指纹", device):
        return "设备指纹"
    return None


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """按事件类型补全 ``order_id`` 与目的地上下文。

    核心引擎沿用 ``receive_id`` 字段保存第三实体标识；在旅游场景中该字段
    承载目的国家/地区，使目的地特征仍能进入原有快照分类。
    """
    order_events = {"机票预订", "酒店预订", "跟团游报名", "退改申请"}
    order_id = request.order_id
    destination = request.receive_id

    if request.event_type in order_events:
        order_id = order_id or request.source_id
        row = (await db.execute(select(OrderInfo.dest_country).where(
            OrderInfo.order_id == order_id
        ))).scalar_one_or_none()
        destination = destination or row
    elif request.event_type == "签证申请":
        row = (await db.execute(select(VisaApplication.dest_country).where(
            VisaApplication.visa_id == request.source_id
        ))).scalar_one_or_none()
        destination = destination or row

    return request.model_copy(update={"order_id": order_id, "receive_id": destination})


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """构造黑名单短路响应；前置保护不写入评估审计表。"""
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
