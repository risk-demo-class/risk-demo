"""Step 4 fixed 25-dimensional manufacturing feature contracts."""

from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.engine.feature import (
    ADDRESS_FEATURE_KEYS,
    FEATURE_KEYS,
    ORDER_FEATURE_KEYS,
    USER_FEATURE_KEYS,
    compute_all_features,
)
from app.engine.ml_model import FEATURE_COLUMNS
from app.models import Dealer, PurchaseOrder, RiskEvent, RiskFeature, WarrantyClaim
from app.schemas import RiskCheckRequest
from app.service.event import _enrich_request
from app.service.validator import validate_risk_check_request


@pytest_asyncio.fixture
async def db_session():
    db_name = os.getenv("STEP4_DB_NAME")
    if not db_name:
        pytest.skip("Set STEP4_DB_NAME to run manufacturing feature integration tests.")

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
        await session.rollback()
    await engine.dispose()


def _assert_feature_contract(features: dict[str, float]) -> None:
    assert len(features) == 25
    assert list(features) == FEATURE_COLUMNS
    assert tuple(features) == FEATURE_KEYS
    assert sum(name.startswith("user_") for name in features) == 14
    assert sum(name.startswith("order_") for name in features) == 8
    assert sum(name.startswith("addr_") for name in features) == 3
    assert tuple(name for name in features if name.startswith("user_")) == USER_FEATURE_KEYS
    assert tuple(name for name in features if name.startswith("order_")) == ORDER_FEATURE_KEYS
    assert tuple(name for name in features if name.startswith("addr_")) == ADDRESS_FEATURE_KEYS
    for value in features.values():
        assert value is not None
        assert math.isfinite(float(value))
    assert features["order_is_night"] in (0.0, 1.0)
    assert features["addr_is_new"] in (0.0, 1.0)


def test_feature_names_exactly_match_frozen_ml_contract():
    assert list(FEATURE_KEYS) == FEATURE_COLUMNS
    assert len(USER_FEATURE_KEYS) == 14
    assert len(ORDER_FEATURE_KEYS) == 8
    assert len(ADDRESS_FEATURE_KEYS) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type,source_id,dealer_id",
    [
        ("下单", "PO001", "DLR001"),
        ("支付", "PO001", "DLR001"),
        ("售后申请", "CLM001", "DLR001"),
        ("物流投诉", "CRR002", "DLR004"),
    ],
)
async def test_all_four_internal_events_return_the_complete_contract(
    db_session, event_type, source_id, dealer_id,
):
    request = RiskCheckRequest(
        event_type=event_type,
        source_id=source_id,
        user_id=dealer_id,
    )
    await validate_risk_check_request(db_session, request)
    request = await _enrich_request(db_session, request)
    features = await compute_all_features(
        db_session,
        request.user_id,
        request.order_id,
        request.receive_id,
    )
    _assert_feature_contract(features)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,dealer_id,source_id,receive_id",
    [
        ("A_normal_purchase", "DLR001", "PO001", "华东-上海中心仓"),
        ("B_new_dealer_large_purchase", "DLR002", "PO002", "华北-北京临时交付点"),
        ("C_normal_warranty", "DLR001", "CLM001", "华东"),
        ("E_high_amount_warranty", "DLR003", "CLM002", "华南"),
        ("F_normal_region_device", "DLR001", "CRR001", "华东"),
        ("G_cross_region_diversion", "DLR004", "CRR002", "华北"),
        ("H_new_dealer_limited_history", "DLR002", "PO002", "华北-北京临时交付点"),
    ],
)
async def test_real_manufacturing_scenarios_always_return_25_dimensions(
    db_session, scenario, dealer_id, source_id, receive_id,
):
    features = await compute_all_features(db_session, dealer_id, source_id, receive_id)
    _assert_feature_contract(features)

    if scenario == "A_normal_purchase":
        assert features["order_total_amount"] == 268000.0
        assert features["addr_is_new"] == 0.0
    elif scenario == "B_new_dealer_large_purchase":
        assert features["order_total_amount"] == 2860000.0
        assert features["order_is_night"] == 1.0
    elif scenario == "C_normal_warranty":
        assert features["order_total_amount"] == 6800.0
        assert features["order_category_count"] == 2.0
    elif scenario == "E_high_amount_warranty":
        assert features["order_total_amount"] == 386000.0
        assert features["user_refund_count"] >= 1.0
    elif scenario == "F_normal_region_device":
        assert features["order_discount_rate"] == 0.0
        assert features["addr_is_new"] == 0.0
    elif scenario == "G_cross_region_diversion":
        assert features["order_discount_rate"] == 1.0
        assert features["addr_is_new"] == 1.0
    elif scenario == "H_new_dealer_limited_history":
        assert features["user_total_orders"] == 1.0
        assert features["user_cancel_count"] < 60.0


@pytest.mark.asyncio
async def test_d_high_frequency_warranty_dealer(db_session):
    for index, amount in enumerate((1200.0, 1800.0, 2400.0), start=1):
        db_session.add(WarrantyClaim(
            claim_id=f"STEP4-FREQ-{index}",
            device_id="DEV005",
            dealer_id="DLR003",
            fault_desc="Step 4 高频保修测试",
            claim_amount=amount,
            photos=[],
            create_time=datetime.now(),
        ))
    await db_session.flush()

    features = await compute_all_features(db_session, "DLR003", "CLM002", "华南")
    _assert_feature_contract(features)
    assert features["user_postsale_count"] >= 4.0
    assert features["user_postsale_rate"] >= 2.0
    assert features["order_sku_count"] >= 4.0


@pytest.mark.asyncio
async def test_risk_scenarios_produce_materially_different_features(db_session):
    normal_purchase = await compute_all_features(
        db_session, "DLR001", "PO001", "华东-上海中心仓",
    )
    risky_purchase = await compute_all_features(
        db_session, "DLR002", "PO002", "华北-北京临时交付点",
    )
    assert normal_purchase["order_total_amount"] != risky_purchase["order_total_amount"]
    assert normal_purchase["order_is_night"] != risky_purchase["order_is_night"]
    assert normal_purchase["user_cancel_count"] != risky_purchase["user_cancel_count"]

    normal_claim = await compute_all_features(db_session, "DLR001", "CLM001", "华东")
    high_claim = await compute_all_features(db_session, "DLR003", "CLM002", "华南")
    assert normal_claim["order_total_amount"] != high_claim["order_total_amount"]
    assert normal_claim["user_refund_count"] != high_claim["user_refund_count"]
    assert normal_claim["user_refund_amount"] != high_claim["user_refund_amount"]

    normal_region = await compute_all_features(db_session, "DLR001", "CRR001", "华东")
    cross_region = await compute_all_features(db_session, "DLR004", "CRR002", "华北")
    assert normal_region["order_discount_rate"] == 0.0
    assert cross_region["order_discount_rate"] == 1.0
    assert normal_region["addr_is_new"] == 0.0
    assert cross_region["addr_is_new"] == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "risk_request,expected_key,expected_value",
    [
        (
            RiskCheckRequest(
                event_type="下单", source_id="PO001", user_id="DLR001",
                event_data={"total_amount": 1, "purchase_amount": 1},
            ),
            "order_total_amount",
            268000.0,
        ),
        (
            RiskCheckRequest(
                event_type="售后申请", source_id="CLM002", user_id="DLR003",
                event_data={"claim_amount": 1, "warranty_count": 999999},
            ),
            "order_total_amount",
            386000.0,
        ),
        (
            RiskCheckRequest(
                event_type="物流投诉", source_id="CRR002", user_id="DLR004",
                event_data={
                    "expected_region": "伪造相同区域",
                    "actual_region": "伪造相同区域",
                    "is_cross_region": 0,
                },
            ),
            "addr_is_new",
            1.0,
        ),
    ],
)
async def test_database_values_override_forged_event_data(
    db_session, risk_request, expected_key, expected_value,
):
    await validate_risk_check_request(db_session, risk_request)
    risk_request = await _enrich_request(db_session, risk_request)
    features = await compute_all_features(
        db_session, risk_request.user_id, risk_request.order_id, risk_request.receive_id,
    )
    _assert_feature_contract(features)
    assert features[expected_key] == expected_value
    if risk_request.event_type == "售后申请":
        assert features["user_postsale_count"] == 1.0
    if risk_request.event_type == "物流投诉":
        assert risk_request.event_data["expected_region"] == "西南"
        assert risk_request.event_data["actual_region"] == "华北"


@pytest.mark.asyncio
async def test_missing_optional_current_object_still_returns_full_zero_filled_slots(db_session):
    features = await compute_all_features(db_session, "DLR002", None, None)
    _assert_feature_contract(features)
    assert all(features[name] == 0.0 for name in ORDER_FEATURE_KEYS)


@pytest.mark.asyncio
async def test_brand_new_dealer_has_safe_zero_history_and_can_run_risk_check(db_session):
    from app.service.event import process_event

    dealer_id = "DLR-STEP4-NEW"
    po_id = "PO-STEP4-NEW"
    db_session.add(Dealer(
        dealer_id=dealer_id,
        name="Step 4 独立验证新经销商",
        level="普通",
        region="东北",
        authorized_at=date.today(),
        contract_end=date.today() + timedelta(days=365),
    ))
    db_session.add(PurchaseOrder(
        po_id=po_id,
        dealer_id=dealer_id,
        total_amount=1000,
        items=[{"model": "TEST-MODEL", "quantity": 1}],
        ship_to="东北",
        payment_term="预付",
        create_time=datetime.now(),
    ))
    await db_session.flush()

    features = await compute_all_features(db_session, dealer_id, po_id, "东北")
    _assert_feature_contract(features)
    assert features["user_total_orders"] == 1.0
    assert features["user_postsale_count"] == 0.0
    assert features["user_postsale_rate"] == 0.0
    assert features["user_refund_count"] == 0.0
    assert features["user_complaint_count"] == 0.0

    response = await process_event(db_session, RiskCheckRequest(
        event_type="下单",
        source_id=po_id,
        user_id=dealer_id,
    ))
    persisted_count = (await db_session.execute(
        select(func.count(RiskFeature.feature_id))
        .where(RiskFeature.event_id == response.event_id)
    )).scalar_one()
    assert persisted_count == 25


@pytest.mark.asyncio
async def test_real_process_event_persists_event_and_25_feature_snapshots(db_session):
    from app.schemas import RiskCheckRequest
    from app.service.event import process_event

    response = await process_event(db_session, RiskCheckRequest(
        event_type="经销商采购提交",
        source_id="PO001",
        user_id="DLR001",
    ))

    event = (await db_session.execute(
        select(RiskEvent).where(RiskEvent.event_id == response.event_id)
    )).scalar_one()
    feature_rows = (await db_session.execute(
        select(RiskFeature)
        .where(RiskFeature.event_id == response.event_id)
        .order_by(RiskFeature.feature_id)
    )).scalars().all()
    feature_count = (await db_session.execute(
        select(func.count(RiskFeature.feature_id)).where(RiskFeature.event_id == response.event_id)
    )).scalar_one()

    assert event.event_type == "下单"
    assert event.event_source_id == "PO001"
    assert event.user_id == "DLR001"
    assert feature_count == 25
    assert len(feature_rows) == 25
    assert {row.feature_name for row in feature_rows} == set(FEATURE_COLUMNS)
    for row in feature_rows:
        assert row.feature_value is not None
        assert math.isfinite(float(row.feature_value))
        if row.feature_name.startswith("user_"):
            assert row.entity_type == "用户"
        elif row.feature_name.startswith("order_"):
            assert row.entity_type == "订单"
        else:
            assert row.feature_name.startswith("addr_")
            assert row.entity_type == "地址"
