import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base
from app.models_business import BUSINESS_TABLE_NAMES
from app.models_risk import RISK_TABLE_NAMES


EXPECTED_TABLES = set(BUSINESS_TABLE_NAMES) | set(RISK_TABLE_NAMES)


def test_exactly_eight_business_and_nine_risk_tables_are_registered() -> None:
    assert len(BUSINESS_TABLE_NAMES) == 8
    assert len(RISK_TABLE_NAMES) == 9
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert len(Base.metadata.tables) == 17


def test_bank_specific_columns_replace_ecommerce_profile_columns() -> None:
    profile_columns = set(Base.metadata.tables["risk_user_profile"].columns.keys())

    assert {"txn_count_30d", "failed_login_count_30d", "debt_ratio"} <= profile_columns
    assert {"total_orders", "total_refunds", "refund_rate"}.isdisjoint(profile_columns)


def test_risk_audit_chain_uses_real_foreign_keys() -> None:
    feature_event_fk = next(iter(Base.metadata.tables["risk_feature"].c.event_id.foreign_keys))
    assessment_event_fk = next(iter(Base.metadata.tables["risk_assessment"].c.event_id.foreign_keys))
    case_assessment_fk = next(iter(Base.metadata.tables["risk_case"].c.assessment_id.foreign_keys))

    assert feature_event_fk.target_fullname == "risk_event.event_id"
    assert assessment_event_fk.target_fullname == "risk_event.event_id"
    assert case_assessment_fk.target_fullname == "risk_assessment.assessment_id"


@pytest.mark.asyncio
async def test_all_tables_can_be_created_in_isolated_database() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

