"""制造业事件处理管道；保持既有 process_event 四步顺序。"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.industry_mapping import get_event_mapping
from app.models import CrossRegionReport, Dealer, Device, PurchaseOrder, WarrantyClaim
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def run_risk_check(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """第 4 步才加载决策引擎；Step 3 测试可安全替换此兼容入口。"""
    from app.engine.decision import run_risk_check as decision_run_risk_check

    return await decision_run_risk_check(db, request)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务校验
    await validate_risk_check_request(db, request)

    # 2. 关联补全
    request = await _enrich_request(db, request)

    # 3. 黑名单检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning(
            "经销商事件撞黑名单: type=%s, dealer_id=%s",
            blocked,
            request.user_id,
        )
        return _blacklist_reject(request, blocked)

    # 4. run_risk_check 七步决策流程（本阶段保持冻结）
    return await run_risk_check(db, request)


async def _check_all_blacklists(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> str | None:
    """按“用户→地址→手机号”检查兼容值，user_id 表示 dealer_id。"""
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    if request.receive_id and await check_blacklist(db, "地址", request.receive_id):
        return "地址"
    event_data = request.event_data or {}
    phone = event_data.get("contact_phone") or event_data.get("reporter_phone")
    if phone and await check_blacklist(db, "手机号", phone):
        return "手机号"
    return None


def _merge_event_data(request: RiskCheckRequest, **authoritative_values: object) -> None:
    mapping = get_event_mapping(request.event_type)
    event_data = dict(request.event_data or {})
    event_data.update({
        "dealer_id": request.user_id,
        "source_id": request.source_id,
        "internal_event_type": request.event_type,
        "industry_event_name": mapping.display_name,
        **authoritative_values,
    })
    request.event_data = event_data


async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """把六表关联信息补入兼容字段和 event_data，不修改 risk_event schema。"""
    mapping = get_event_mapping(request.event_type)

    if mapping.source_entity == "purchase_order":
        row = (await db.execute(
            select(
                PurchaseOrder.po_id,
                PurchaseOrder.dealer_id,
                PurchaseOrder.ship_to,
                Dealer.region,
            )
            .join(Dealer, Dealer.dealer_id == PurchaseOrder.dealer_id)
            .where(PurchaseOrder.po_id == request.source_id)
        )).first()
        if row:
            request.order_id = request.order_id or row.po_id
            request.receive_id = request.receive_id or row.ship_to
            _merge_event_data(
                request,
                purchase_order_id=row.po_id,
                ship_to=row.ship_to,
                region=row.region,
            )

    elif mapping.source_entity == "warranty_claim":
        row = (await db.execute(
            select(
                WarrantyClaim.claim_id,
                WarrantyClaim.dealer_id,
                WarrantyClaim.device_id,
                Device.sn,
                Device.model,
                Dealer.region,
            )
            .join(Device, Device.device_id == WarrantyClaim.device_id)
            .join(Dealer, Dealer.dealer_id == WarrantyClaim.dealer_id)
            .where(WarrantyClaim.claim_id == request.source_id)
        )).first()
        if row:
            request.order_id = request.order_id or row.claim_id
            request.receive_id = request.receive_id or row.region
            _merge_event_data(
                request,
                warranty_claim_id=row.claim_id,
                device_id=row.device_id,
                device_sn=row.sn,
                device_model=row.model,
                region=row.region,
            )

    elif mapping.source_entity == "cross_region_report":
        row = (await db.execute(
            select(
                CrossRegionReport.report_id,
                CrossRegionReport.device_id,
                CrossRegionReport.expected_region,
                CrossRegionReport.actual_region,
                Device.dealer_id,
                Device.sn,
                Device.model,
            )
            .join(Device, Device.device_id == CrossRegionReport.device_id)
            .where(CrossRegionReport.report_id == request.source_id)
        )).first()
        if row:
            dealer_id = row.dealer_id or (request.event_data or {}).get("dealer_id")
            request.order_id = request.order_id or row.report_id
            request.receive_id = request.receive_id or row.actual_region
            _merge_event_data(
                request,
                dealer_id=dealer_id,
                cross_region_report_id=row.report_id,
                device_id=row.device_id,
                device_sn=row.sn,
                device_model=row.model,
                expected_region=row.expected_region,
                actual_region=row.actual_region,
                region=row.actual_region,
            )

    return request


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """黑名单短路不写核心风控表，保持原有保护动作语义。"""
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
