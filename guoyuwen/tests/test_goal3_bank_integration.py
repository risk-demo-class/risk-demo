import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import get_test_engine_async
from app.models import RiskFeature
from app.schemas import RiskCheckRequest
from app.service.event import process_event


pytestmark = pytest.mark.skipif(
    os.getenv("GOAL3_DB_TEST") != "1",
    reason="仅在隔离 bank_risk_test 上运行",
)


SAMPLES = [
    ("登录", "DEMO_LOGIN_006", "DEMO_USR_006"),
    ("转账", "DEMO_TXN_003", "DEMO_USR_002"),
    ("贷款申请", "DEMO_LOAN_003", "DEMO_USR_010"),
    ("绑卡", "DEMO_CARD_003", "DEMO_USR_003"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("event_type", "source_id", "user_id"), SAMPLES)
async def test_four_bank_events_persist_complete_25_feature_snapshot(
    event_type, source_id, user_id
):
    engine = get_test_engine_async()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            response = await process_event(
                db,
                RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=user_id,
                    event_data={"smoke": "goal3"},
                ),
            )
            assert len(response.features) == 25
            count = (
                await db.execute(
                    select(func.count())
                    .select_from(RiskFeature)
                    .where(RiskFeature.event_id == response.event_id)
                )
            ).scalar_one()
            assert count == 25
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_id", "user_id", "expected_rule"),
    [
        ("DEMO_TXN_001", "DEMO_USR_002", "BANK_R001"),
        ("DEMO_TXN_003", "DEMO_USR_002", "BANK_R002"),
        ("DEMO_TXN_008", "DEMO_USR_010", "BANK_R003"),
    ],
)
async def test_three_distinct_database_rules_hit(source_id, user_id, expected_rule):
    engine = get_test_engine_async()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            response = await process_event(
                db,
                RiskCheckRequest(
                    event_type="转账", source_id=source_id, user_id=user_id
                ),
            )
            assert expected_rule in {item.rule_id for item in response.triggered_rules}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_black_card_precheck_rejects_without_rule_evaluation():
    engine = get_test_engine_async()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            response = await process_event(
                db,
                RiskCheckRequest(
                    event_type="转账",
                    source_id="DEMO_TXN_017",
                    user_id="DEMO_USR_009",
                ),
            )
            assert response.decision == "拒绝"
            assert response.blocked_by == "银行卡号"
            assert response.rule_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_normal_login_passes():
    engine = get_test_engine_async()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            response = await process_event(
                db,
                RiskCheckRequest(
                    event_type="登录",
                    source_id="DEMO_LOGIN_006",
                    user_id="DEMO_USR_006",
                ),
            )
            assert response.decision == "通过"
            assert response.rule_count == 0
    finally:
        await engine.dispose()
