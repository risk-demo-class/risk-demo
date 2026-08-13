"""真实 MySQL 反射验收：17 表、业务 ORM 一致性与核心 9 表冻结。"""

import os

import pytest
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    create_engine,
    inspect,
)
from sqlalchemy.schema import UniqueConstraint

from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)

BUSINESS_MODELS = (
    UserInfo,
    BankCard,
    Transaction,
    LoanApplication,
    LoginLog,
    DeviceFingerprint,
    IpGeoLocation,
    BlacklistExtra,
)

CORE_TABLE_COLUMNS = {
    "risk_rule": {
        "rule_id",
        "rule_name",
        "rule_category",
        "event_type",
        "rule_condition",
        "risk_level",
        "risk_score",
        "action",
        "is_enabled",
        "priority",
        "description",
        "create_time",
        "update_time",
        "deleted_at",
    },
    "risk_event": {
        "event_id",
        "event_type",
        "event_source_id",
        "user_id",
        "event_data",
        "create_time",
    },
    "risk_feature": {
        "feature_id",
        "event_id",
        "entity_type",
        "entity_id",
        "feature_name",
        "feature_value",
        "compute_time",
    },
    "risk_assessment": {
        "assessment_id",
        "event_id",
        "user_id",
        "rule_results",
        "rule_count",
        "final_score",
        "risk_level",
        "decision",
        "ml_score",
        "ml_decision",
        "create_time",
    },
    "risk_case": {
        "case_id",
        "assessment_id",
        "user_id",
        "case_status",
        "case_category",
        "risk_detail",
        "source_id",
        "event_type",
        "reviewer",
        "review_comment",
        "review_time",
        "create_time",
        "update_time",
    },
    "risk_blacklist": {
        "blacklist_id",
        "blacklist_type",
        "blacklist_value",
        "reason",
        "expire_time",
        "create_time",
        "deleted_at",
    },
    "risk_user_profile": {
        "user_id",
        "risk_score",
        "risk_level",
        "total_orders",
        "total_refunds",
        "refund_rate",
        "avg_order_amount",
        "address_count",
        "complaint_count",
        "assessment_count",
        "last_assessment_time",
        "profile_data",
        "update_time",
    },
    "risk_action_log": {
        "log_id",
        "operator",
        "action_type",
        "target_type",
        "target_id",
        "before_value",
        "after_value",
        "ip",
        "remark",
        "create_time",
    },
    "risk_alert": {
        "alert_id",
        "alert_type",
        "alert_level",
        "alert_title",
        "alert_content",
        "metric_name",
        "metric_value",
        "threshold",
        "status",
        "handler",
        "resolve_time",
        "create_time",
    },
}


pytestmark = pytest.mark.skipif(
    not os.getenv("DDL_CHECK_ENABLED"),
    reason="真实 MySQL DDL 验收默认关闭；设置 DDL_CHECK_ENABLED=1 启用",
)


def _normalize_default(value):
    if value is None:
        return None
    normalized = (
        str(value)
        .strip()
        .strip("'")
        .lower()
        .replace("current_timestamp()", "current_timestamp")
    )
    return normalized


def _assert_type_matches(orm_type, live_type, label):
    if isinstance(orm_type, Enum):
        assert isinstance(live_type, Enum), label
        assert tuple(live_type.enums) == tuple(orm_type.enums), label
    elif isinstance(orm_type, Boolean):
        assert "TINYINT" in str(live_type).upper(), label
    elif isinstance(orm_type, BigInteger):
        assert isinstance(live_type, BigInteger), label
    elif isinstance(orm_type, Integer):
        assert isinstance(live_type, Integer), label
    elif isinstance(orm_type, Numeric):
        assert isinstance(live_type, Numeric), label
        assert (live_type.precision, live_type.scale) == (
            orm_type.precision,
            orm_type.scale,
        ), label
    elif isinstance(orm_type, String):
        assert isinstance(live_type, String), label
        assert live_type.length == orm_type.length, label
    elif isinstance(orm_type, DateTime):
        assert isinstance(live_type, DateTime), label
    else:
        raise AssertionError(f"未覆盖的 ORM 类型: {label}={orm_type}")


@pytest.fixture(scope="module")
def inspector():
    from app.config import settings

    engine = create_engine(
        settings.get_database_url_async().replace("+aiomysql", "+pymysql")
    )
    try:
        yield inspect(engine)
    finally:
        engine.dispose()


def test_exactly_eight_business_and_nine_core_tables(inspector):
    expected = {model.__tablename__ for model in BUSINESS_MODELS} | set(
        CORE_TABLE_COLUMNS
    )
    assert set(inspector.get_table_names()) == expected


@pytest.mark.parametrize(
    "model", BUSINESS_MODELS, ids=lambda model: model.__tablename__
)
def test_business_orm_matches_live_ddl(inspector, model):
    table_name = model.__tablename__
    live_columns = {
        column["name"]: column for column in inspector.get_columns(table_name)
    }
    assert set(live_columns) == set(model.__table__.columns.keys())

    for orm_column in model.__table__.columns:
        label = f"{table_name}.{orm_column.name}"
        live_column = live_columns[orm_column.name]
        assert live_column["nullable"] == orm_column.nullable, label
        _assert_type_matches(orm_column.type, live_column["type"], label)
        orm_default = _normalize_default(
            orm_column.server_default.arg
            if orm_column.server_default is not None
            else None
        )
        assert _normalize_default(live_column["default"]) == orm_default, label

    expected_indexes = {index.name for index in model.__table__.indexes}
    expected_indexes.update(
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    )
    live_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    live_indexes.update(
        item["name"] for item in inspector.get_unique_constraints(table_name)
    )
    assert expected_indexes <= live_indexes


@pytest.mark.parametrize("table_name", sorted(CORE_TABLE_COLUMNS))
def test_core_table_columns_remain_frozen(inspector, table_name):
    assert {
        column["name"] for column in inspector.get_columns(table_name)
    } == CORE_TABLE_COLUMNS[table_name]
