"""
旅游行业风控系统 - AI Agent 工具集。

保持参考项目“Agent 调工具”的能力，但业务查询改为旅游表。
"""
import json
import logging
from datetime import datetime, timedelta

import ulid
from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.engine.feature import compute_user_features
from app.models import (
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    TravelComplaint,
    TravelRefund,
    VisaApplication,
)
from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service.case import add_blacklist, check_blacklist, get_blacklist, get_case_list, get_user_profile
from app.service.event import process_event

logger = logging.getLogger(__name__)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


async def _safe_call(label: str, impl, **kwargs) -> str:
    try:
        async with AsyncSessionLocal() as db:
            return await impl(db=db, **kwargs)
    except Exception as e:
        error_id = f"err_{ulid.new().str.lower()[:12]}"
        logger.exception("%s 执行失败 [error_id=%s]", label, error_id)
        return f"{label}失败: {e} (error_id={error_id})"


def _row_to_dict(row) -> dict:
    item = {}
    for key, val in row._mapping.items():
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "__float__"):
            val = float(val)
        item[key] = val
    return item


async def _risk_check_impl(*, db: AsyncSession, user_id: str, event_type: str, source_id: str) -> str:
    req = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id)
    result = await process_event(db, req)
    return _json({
        "assessment_id": result.assessment_id,
        "event_id": result.event_id,
        "user_id": result.user_id,
        "final_score": result.final_score,
        "risk_level": result.risk_level,
        "decision": result.decision,
        "rule_count": result.rule_count,
        "blocked_by": result.blocked_by,
        "triggered_rules": [r.model_dump() for r in result.triggered_rules],
    })


async def _case_query_impl(*, db: AsyncSession, status: str = "", limit: int = 10) -> str:
    page = await get_case_list(db, status=status or None, page=1, page_size=limit)
    return _json([item.model_dump() for item in page.items])


async def _profile_query_impl(*, db: AsyncSession, user_id: str) -> str:
    profile = await get_user_profile(db, user_id)
    if profile:
        return profile.model_dump_json(indent=2)
    return _json({"user_id": user_id, "features": await compute_user_features(db, user_id)})


async def _blacklist_impl(
    *, db: AsyncSession, action: str, blacklist_type: str = "", value: str = "", reason: str = "",
) -> str:
    if action == "check":
        return _json({"hit": await check_blacklist(db, blacklist_type, value)})
    if action == "add":
        created = await add_blacklist(db, BlacklistCreate(
            blacklist_type=blacklist_type,
            blacklist_value=value,
            reason=reason or "AI Agent 添加",
        ))
        return created.model_dump_json(indent=2)
    if action == "list":
        page = await get_blacklist(db, page=1, page_size=20)
        return _json([item.model_dump() for item in page.items])
    return "不支持的 action，请使用 check/add/list"


async def _dashboard_impl(*, db: AsyncSession) -> str:
    today = datetime.now() - timedelta(days=1)
    total = (await db.execute(select(func.count()).select_from(RiskAssessment))).scalar() or 0
    recent = (await db.execute(
        select(func.count()).select_from(RiskAssessment).where(RiskAssessment.create_time >= today)
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status.in_(["待审核", "审核中"]))
    )).scalar() or 0
    rejected = (await db.execute(
        select(func.count()).select_from(RiskAssessment).where(RiskAssessment.decision == "拒绝")
    )).scalar() or 0
    return _json({"total_assessments": total, "recent_24h": recent, "pending_cases": pending, "rejected": rejected})


async def _biz_data_impl(*, db: AsyncSession, query_type: str, user_id: str = "", order_id: str = "", limit: int = 10) -> str:
    if query_type == "user_orders":
        stmt = select(
            OrderInfo.order_id, OrderInfo.order_type, OrderInfo.total_amount, OrderInfo.dest_country,
            OrderInfo.dest_city, OrderInfo.depart_date, OrderInfo.order_status, OrderInfo.create_time,
        ).where(OrderInfo.user_id == user_id).order_by(OrderInfo.create_time.desc()).limit(limit)
    elif query_type == "order_passengers":
        stmt = select(
            PassengerInfo.passenger_id, PassengerInfo.name, PassengerInfo.id_type,
            PassengerInfo.nationality, PassengerInfo.document_status,
        ).where(PassengerInfo.order_id == order_id).limit(limit)
    elif query_type == "visas":
        stmt = select(
            VisaApplication.visa_id, VisaApplication.order_id, VisaApplication.dest_country,
            VisaApplication.visa_status, VisaApplication.reject_history, VisaApplication.material_change_count,
        ).where(VisaApplication.user_id == user_id).limit(limit)
    elif query_type == "hotels":
        stmt = select(
            BookingHotel.booking_id, BookingHotel.order_id, BookingHotel.hotel_name,
            BookingHotel.city, BookingHotel.check_in, BookingHotel.check_out,
        ).where(BookingHotel.order_id == order_id).limit(limit)
    elif query_type == "flights":
        stmt = select(
            BookingFlight.booking_id, BookingFlight.order_id, BookingFlight.flight_no,
            BookingFlight.depart_airport, BookingFlight.arrive_airport, BookingFlight.ticket_count,
        ).where(BookingFlight.order_id == order_id).limit(limit)
    elif query_type == "refunds":
        stmt = select(
            TravelRefund.refund_id, TravelRefund.order_id, TravelRefund.refund_type,
            TravelRefund.refund_amount, TravelRefund.refund_status,
        ).where(TravelRefund.user_id == user_id).limit(limit)
    elif query_type == "complaints":
        stmt = select(
            TravelComplaint.complaint_id, TravelComplaint.order_id, TravelComplaint.complaint_type,
            TravelComplaint.compensation_amount, TravelComplaint.complaint_status,
        ).where(TravelComplaint.user_id == user_id).limit(limit)
    else:
        return "query_type 可选: user_orders/order_passengers/visas/hotels/flights/refunds/complaints"

    rows = list((await db.execute(stmt)).all())
    return _json([_row_to_dict(row) for row in rows])


@tool
def risk_check(user_id: str, event_type: str, source_id: str) -> str:
    """执行旅游风控检查。event_type 可选旅游下单/机票预订/酒店预订/签证申请/支付/售后申请/投诉/出行前核验。"""
    import asyncio
    return asyncio.run(_safe_call("风控检查", _risk_check_impl, user_id=user_id, event_type=event_type, source_id=source_id))


@tool
def query_cases(status: str = "", limit: int = 10) -> str:
    """查询风险案件列表。"""
    import asyncio
    return asyncio.run(_safe_call("案件查询", _case_query_impl, status=status, limit=limit))


@tool
def query_user_profile(user_id: str) -> str:
    """查询用户风险画像或实时用户特征。"""
    import asyncio
    return asyncio.run(_safe_call("画像查询", _profile_query_impl, user_id=user_id))


@tool
def manage_blacklist(action: str, blacklist_type: str = "", value: str = "", reason: str = "") -> str:
    """管理黑名单。action=check/add/list，类型支持用户/手机号/护照号/身份证号/支付账号/设备指纹/IP/订单。"""
    import asyncio
    return asyncio.run(_safe_call("黑名单管理", _blacklist_impl, action=action, blacklist_type=blacklist_type, value=value, reason=reason))


@tool
def dashboard_stats() -> str:
    """查询风控仪表盘核心指标。"""
    import asyncio
    return asyncio.run(_safe_call("仪表盘统计", _dashboard_impl))


@tool
def query_business_data(query_type: str, user_id: str = "", order_id: str = "", limit: int = 10) -> str:
    """查询旅游业务数据。query_type=user_orders/order_passengers/visas/hotels/flights/refunds/complaints。"""
    import asyncio
    return asyncio.run(_safe_call("业务数据查询", _biz_data_impl, query_type=query_type, user_id=user_id, order_id=order_id, limit=limit))


RISK_TOOLS = [risk_check, query_cases, query_user_profile, manage_blacklist]

# 兼容参考项目里的旧命名，避免路由或脚本迁移时导入失败。
query_dashboard_stats = dashboard_stats

DATA_TOOLS = [dashboard_stats, query_business_data]
ALL_TOOLS = RISK_TOOLS + DATA_TOOLS
