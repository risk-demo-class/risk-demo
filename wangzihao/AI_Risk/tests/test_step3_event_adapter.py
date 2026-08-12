"""Step 3 manufacturing event validation, enrichment, and pipeline contracts."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.industry_mapping import EVENT_MAPPINGS, EXTERNAL_EVENT_ALIASES
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module
from app.service import validator as validator_module


def _response(user_id: str) -> RiskCheckResponse:
    from datetime import datetime

    return RiskCheckResponse(
        assessment_id="mock",
        event_id="mock",
        user_id=user_id,
        final_score=0,
        risk_level="低",
        decision="通过",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
    )


@pytest_asyncio.fixture
async def db_session():
    db_name = os.getenv("STEP3_DB_NAME")
    if not db_name:
        pytest.skip("Set STEP3_DB_NAME to run manufacturing event integration tests.")

    from app.config import settings

    url = URL.create(
        "mysql+aiomysql",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=db_name,
        query={"charset": "utf8mb4"},
    )
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.parametrize("external,internal", EXTERNAL_EVENT_ALIASES.items())
def test_external_event_names_normalize_to_frozen_internal_codes(external, internal):
    request = RiskCheckRequest(event_type=external, source_id="SOURCE", user_id="DLR001")
    assert request.event_type == internal


def test_final_event_source_mapping_contract():
    assert {
        event_type: (mapping.source_table, mapping.source_id_field)
        for event_type, mapping in EVENT_MAPPINGS.items()
    } == {
        "下单": ("purchase_order", "po_id"),
        "支付": ("purchase_order", "po_id"),
        "售后申请": ("warranty_claim", "claim_id"),
        "物流投诉": ("cross_region_report", "report_id"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["经销商采购提交", "采购付款", "采购确认"])
async def test_a_normal_purchase_and_payment_pass_validator(db_session, event_type):
    request = RiskCheckRequest(event_type=event_type, source_id="PO001", user_id="DLR001")
    await validator_module.validate_risk_check_request(db_session, request)


@pytest.mark.asyncio
async def test_b_missing_purchase_order_has_clear_failure(db_session):
    request = RiskCheckRequest(event_type="下单", source_id="PO-NOT-FOUND", user_id="DLR001")
    with pytest.raises(HTTPException) as exc_info:
        await validator_module.validate_risk_check_request(db_session, request)
    assert exc_info.value.status_code == 404
    assert "采购订单ID不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_c_purchase_order_owned_by_another_dealer_is_rejected(db_session):
    request = RiskCheckRequest(event_type="下单", source_id="PO001", user_id="DLR002")
    with pytest.raises(HTTPException) as exc_info:
        await validator_module.validate_risk_check_request(db_session, request)
    assert exc_info.value.status_code == 403
    assert "与请求经销商 DLR002 不一致" in exc_info.value.detail


@pytest.mark.asyncio
async def test_d_normal_warranty_claim_passes_validator(db_session):
    request = RiskCheckRequest(event_type="设备保修申请", source_id="CLM001", user_id="DLR001")
    await validator_module.validate_risk_check_request(db_session, request)


@pytest.mark.asyncio
async def test_e_missing_warranty_claim_has_clear_failure(db_session):
    request = RiskCheckRequest(event_type="售后申请", source_id="CLM-NOT-FOUND", user_id="DLR001")
    with pytest.raises(HTTPException) as exc_info:
        await validator_module.validate_risk_check_request(db_session, request)
    assert exc_info.value.status_code == 404
    assert "保修申请ID不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_f_warranty_claim_dealer_mismatch_is_rejected(db_session):
    request = RiskCheckRequest(event_type="售后申请", source_id="CLM001", user_id="DLR002")
    with pytest.raises(HTTPException) as exc_info:
        await validator_module.validate_risk_check_request(db_session, request)
    assert exc_info.value.status_code == 403
    assert "与请求经销商 DLR002 不一致" in exc_info.value.detail


@pytest.mark.asyncio
async def test_g_warranty_claim_with_missing_device_is_rejected_defensively():
    class _Result:
        def __init__(self, *, row=None, scalar=None):
            self._row = row
            self._scalar = scalar

        def first(self):
            return self._row

        def scalar(self):
            return self._scalar

    db = SimpleNamespace(execute=AsyncMock(side_effect=[
        _Result(row=SimpleNamespace(dealer_id="DLR001", device_id="DEV-MISSING")),
        _Result(scalar=0),
    ]))
    request = RiskCheckRequest(event_type="售后申请", source_id="CLM-BROKEN", user_id="DLR001")
    with pytest.raises(HTTPException) as exc_info:
        await validator_module._validate_warranty_claim(db, request)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "设备ID不存在: DEV-MISSING"


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["串货举报", "跨区域检查"])
async def test_h_normal_cross_region_report_passes_validator(db_session, event_type):
    request = RiskCheckRequest(event_type=event_type, source_id="CRR002", user_id="DLR004")
    await validator_module.validate_risk_check_request(db_session, request)


@pytest.mark.asyncio
async def test_i_missing_cross_region_report_has_clear_failure(db_session):
    request = RiskCheckRequest(event_type="物流投诉", source_id="CRR-NOT-FOUND", user_id="DLR001")
    with pytest.raises(HTTPException) as exc_info:
        await validator_module.validate_risk_check_request(db_session, request)
    assert exc_info.value.status_code == 404
    assert "串货举报ID不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cross_region_report_can_use_event_data_dealer_when_device_is_unassigned():
    class _Result:
        def __init__(self, row):
            self._row = row

        def first(self):
            return self._row

    db = SimpleNamespace(execute=AsyncMock(side_effect=[
        _Result(SimpleNamespace(device_id="DEV006")),
        _Result(SimpleNamespace(device_id="DEV006", dealer_id=None)),
    ]))
    request = RiskCheckRequest(
        event_type="串货举报",
        source_id="CRR-UNASSIGNED",
        user_id="DLR001",
        event_data={"dealer_id": "DLR001"},
    )
    await validator_module._validate_cross_region_report(db, request)


@pytest.mark.asyncio
async def test_purchase_enrichment_provides_compatibility_context(db_session):
    request = RiskCheckRequest(
        event_type="经销商采购提交",
        source_id="PO001",
        user_id="DLR001",
        event_data={"caller_note": "keep-me"},
    )
    enriched = await event_module._enrich_request(db_session, request)
    assert enriched.order_id == "PO001"
    assert enriched.receive_id == "华东-上海中心仓"
    assert enriched.event_data == {
        "caller_note": "keep-me",
        "dealer_id": "DLR001",
        "source_id": "PO001",
        "internal_event_type": "下单",
        "industry_event_name": "经销商采购提交",
        "purchase_order_id": "PO001",
        "ship_to": "华东-上海中心仓",
        "region": "华东",
    }


@pytest.mark.asyncio
async def test_warranty_enrichment_provides_device_and_claim_context(db_session):
    request = RiskCheckRequest(event_type="设备保修申请", source_id="CLM001", user_id="DLR001")
    enriched = await event_module._enrich_request(db_session, request)
    assert enriched.order_id == "CLM001"
    assert enriched.receive_id == "华东"
    assert enriched.event_data["warranty_claim_id"] == "CLM001"
    assert enriched.event_data["device_id"] == "DEV001"
    assert enriched.event_data["device_sn"] == "SN-CNC-A10001"
    assert enriched.event_data["region"] == "华东"


@pytest.mark.asyncio
async def test_cross_region_enrichment_provides_report_and_region_context(db_session):
    request = RiskCheckRequest(event_type="串货举报", source_id="CRR002", user_id="DLR004")
    enriched = await event_module._enrich_request(db_session, request)
    assert enriched.order_id == "CRR002"
    assert enriched.receive_id == "华北"
    assert enriched.event_data["cross_region_report_id"] == "CRR002"
    assert enriched.event_data["device_id"] == "DEV004"
    assert enriched.event_data["expected_region"] == "西南"
    assert enriched.event_data["actual_region"] == "华北"


@pytest.mark.asyncio
async def test_process_event_keeps_all_four_calls_in_order(monkeypatch):
    calls = []
    request = RiskCheckRequest(event_type="下单", source_id="PO001", user_id="DLR001")

    async def validate(db, req):
        calls.append("validate")

    async def enrich(db, req):
        calls.append("enrich")
        return req

    async def blacklist(db, req):
        calls.append("blacklist")
        return None

    async def decide(db, req):
        calls.append("run_risk_check")
        return _response(req.user_id)

    monkeypatch.setattr(event_module, "validate_risk_check_request", validate)
    monkeypatch.setattr(event_module, "_enrich_request", enrich)
    monkeypatch.setattr(event_module, "_check_all_blacklists", blacklist)
    monkeypatch.setattr(event_module, "run_risk_check", decide)

    response = await event_module.process_event(SimpleNamespace(), request)
    assert response.decision == "通过"
    assert calls == ["validate", "enrich", "blacklist", "run_risk_check"]


@pytest.mark.asyncio
async def test_j_blacklisted_dealer_short_circuits_at_step_three(monkeypatch):
    calls = []
    request = RiskCheckRequest(event_type="下单", source_id="PO001", user_id="DLR001")

    async def validate(db, req):
        calls.append("validate")

    async def enrich(db, req):
        calls.append("enrich")
        return req

    async def blacklist(db, req):
        calls.append("blacklist")
        return "用户"

    async def must_not_run(db, req):
        calls.append("run_risk_check")
        raise AssertionError("blacklisted dealer must not reach run_risk_check")

    monkeypatch.setattr(event_module, "validate_risk_check_request", validate)
    monkeypatch.setattr(event_module, "_enrich_request", enrich)
    monkeypatch.setattr(event_module, "_check_all_blacklists", blacklist)
    monkeypatch.setattr(event_module, "run_risk_check", must_not_run)

    response = await event_module.process_event(SimpleNamespace(), request)
    assert response.decision == "拒绝"
    assert response.blocked_by == "用户"
    assert calls == ["validate", "enrich", "blacklist"]


@pytest.mark.asyncio
async def test_dealer_id_uses_frozen_user_blacklist_type(monkeypatch):
    calls = []

    async def fake_check(db, blacklist_type, value):
        calls.append((blacklist_type, value))
        return blacklist_type == "用户" and value == "DLR001"

    monkeypatch.setattr(event_module, "check_blacklist", fake_check)
    request = RiskCheckRequest(event_type="下单", source_id="PO001", user_id="DLR001")
    assert await event_module._check_all_blacklists(SimpleNamespace(), request) == "用户"
    assert calls == [("用户", "DLR001")]
