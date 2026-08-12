"""Step 2 manufacturing business-model, DDL, and seed-data contracts."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import Enum
from sqlalchemy.dialects import mysql


ROOT = Path(__file__).resolve().parent.parent
BUSINESS_TABLES = (
    "dealer",
    "device",
    "purchase_order",
    "warranty_claim",
    "cross_region_report",
    "blacklist_extra",
)

BUSINESS_MODELS = {
    "dealer": "Dealer",
    "device": "Device",
    "purchase_order": "PurchaseOrder",
    "warranty_claim": "WarrantyClaim",
    "cross_region_report": "CrossRegionReport",
    "blacklist_extra": "BlacklistExtra",
}

EXPECTED_COLUMNS = {
    "dealer": ("dealer_id", "name", "level", "region", "authorized_at", "contract_end"),
    "device": ("device_id", "sn", "model", "batch_no", "factory_at", "warranty_end", "dealer_id"),
    "purchase_order": ("po_id", "dealer_id", "total_amount", "items", "ship_to", "payment_term", "create_time"),
    "warranty_claim": ("claim_id", "device_id", "dealer_id", "fault_desc", "claim_amount", "photos", "create_time"),
    "cross_region_report": ("report_id", "device_id", "expected_region", "actual_region", "reporter_id", "create_time"),
    "blacklist_extra": ("entry_id", "type", "value", "reason", "expire_at"),
}

EXPECTED_NULLABLE = {
    "dealer": set(),
    "device": {"dealer_id"},
    "purchase_order": set(),
    "warranty_claim": {"photos"},
    "cross_region_report": set(),
    "blacklist_extra": {"expire_at"},
}

EXPECTED_INDEXES = {
    "dealer": {
        ("uq_dealer_name", ("name",), True),
        ("idx_dealer_region", ("region",), False),
        ("idx_dealer_contract_end", ("contract_end",), False),
    },
    "device": {
        ("uq_device_sn", ("sn",), True),
        ("idx_device_model", ("model",), False),
        ("idx_device_batch_no", ("batch_no",), False),
        ("idx_device_dealer_id", ("dealer_id",), False),
    },
    "purchase_order": {
        ("idx_purchase_order_dealer_id", ("dealer_id",), False),
        ("idx_purchase_order_create_time", ("create_time",), False),
        ("idx_purchase_order_total_amount", ("total_amount",), False),
    },
    "warranty_claim": {
        ("idx_warranty_claim_device_id", ("device_id",), False),
        ("idx_warranty_claim_dealer_id", ("dealer_id",), False),
        ("idx_warranty_claim_create_time", ("create_time",), False),
    },
    "cross_region_report": {
        ("idx_cross_region_report_device_id", ("device_id",), False),
        ("idx_cross_region_report_regions", ("expected_region", "actual_region"), False),
        ("idx_cross_region_report_create_time", ("create_time",), False),
    },
    "blacklist_extra": {
        ("uq_blacklist_extra_type_value", ("type", "value"), True),
        ("idx_blacklist_extra_expire_at", ("expire_at",), False),
    },
}

EXPECTED_FOREIGN_KEYS = {
    "dealer": set(),
    "device": {("fk_device_dealer", ("dealer_id",), "dealer", ("dealer_id",))},
    "purchase_order": {("fk_purchase_order_dealer", ("dealer_id",), "dealer", ("dealer_id",))},
    "warranty_claim": {
        ("fk_warranty_claim_device", ("device_id",), "device", ("device_id",)),
        ("fk_warranty_claim_dealer", ("dealer_id",), "dealer", ("dealer_id",)),
    },
    "cross_region_report": {
        ("fk_cross_region_report_device", ("device_id",), "device", ("device_id",)),
    },
    "blacklist_extra": set(),
}

EXPECTED_SEED_COUNTS = {
    "dealer": 4,
    "device": 6,
    "purchase_order": 4,
    "warranty_claim": 3,
    "cross_region_report": 3,
    "blacklist_extra": 3,
}


def _ddl_table_names() -> tuple[str, ...]:
    sql = (ROOT / "sql" / "init_business_tables.sql").read_text(encoding="utf-8")
    return tuple(re.findall(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`([^`]+)`",
        sql,
        flags=re.IGNORECASE,
    ))


def _model_classes():
    from app import models_business

    return {
        table: getattr(models_business, class_name)
        for table, class_name in BUSINESS_MODELS.items()
    }


def _orm_indexes(table) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (index.name, tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }


def _orm_foreign_keys(table) -> set[tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            constraint.name,
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }


def _normalize_type(value):
    if isinstance(value, Enum):
        return "enum", tuple(value.enums)
    if hasattr(value, "compile"):
        value = value.compile(dialect=mysql.dialect())
    return str(value).lower().replace(" ", "").replace("numeric(", "decimal(")


def _normalize_default(value):
    if value is None:
        return None
    if hasattr(value, "arg"):
        value = value.arg
    normalized = str(value).strip().lower()
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1].strip()
    normalized = normalized.strip("'").replace("()", "")
    return "current_timestamp" if normalized == "now" else normalized


def test_exactly_six_business_tables_in_orm_and_ddl():
    models = _model_classes()
    assert tuple(models) == BUSINESS_TABLES
    assert tuple(model.__table__.name for model in models.values()) == BUSINESS_TABLES
    assert _ddl_table_names() == BUSINESS_TABLES


@pytest.mark.parametrize("table_name", BUSINESS_TABLES)
def test_orm_business_contract(table_name):
    table = _model_classes()[table_name].__table__
    assert tuple(table.columns.keys()) == EXPECTED_COLUMNS[table_name]
    assert {column.name for column in table.columns if column.nullable} == EXPECTED_NULLABLE[table_name]
    assert len(table.primary_key.columns) == 1
    assert _orm_indexes(table) == EXPECTED_INDEXES[table_name]
    assert _orm_foreign_keys(table) == EXPECTED_FOREIGN_KEYS[table_name]


def test_business_sql_does_not_select_a_hard_coded_database():
    for filename in ("init_business_tables.sql", "init_business_data.sql"):
        sql = (ROOT / "sql" / filename).read_text(encoding="utf-8")
        assert not re.search(r"^\s*USE\s+", sql, flags=re.IGNORECASE | re.MULTILINE)


def test_models_hub_exports_only_six_business_models_plus_nine_risk_models():
    import app.models as models

    assert set(BUSINESS_MODELS.values()).issubset(models.__all__)
    assert len(models.__all__) == 15


@pytest.mark.skipif(
    not os.getenv("STEP2_DB_NAME"),
    reason="Set STEP2_DB_NAME to run integration checks against an isolated database.",
)
def test_initialized_database_matches_orm_and_seed_contract():
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import URL

    from app.config import settings
    from test_step1_migration_contract import CORE_TABLE_COLUMNS

    db_name = os.environ["STEP2_DB_NAME"]
    url = URL.create(
        "mysql+pymysql",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=db_name,
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(url)
    inspector = inspect(engine)
    models = _model_classes()

    try:
        actual_tables = set(inspector.get_table_names())
        assert actual_tables == set(BUSINESS_TABLES) | set(CORE_TABLE_COLUMNS)

        for table_name, model in models.items():
            table = model.__table__
            actual_columns = inspector.get_columns(table_name)
            assert tuple(column["name"] for column in actual_columns) == EXPECTED_COLUMNS[table_name]
            assert {column["name"] for column in actual_columns if column["nullable"]} == EXPECTED_NULLABLE[table_name]
            assert {
                column["name"]: _normalize_type(column["type"])
                for column in actual_columns
            } == {
                column.name: _normalize_type(column.type)
                for column in table.columns
            }
            assert {
                column["name"]: _normalize_default(column.get("default"))
                for column in actual_columns
            } == {
                column.name: _normalize_default(column.server_default)
                for column in table.columns
            }

            actual_pk = tuple(inspector.get_pk_constraint(table_name)["constrained_columns"])
            expected_pk = tuple(table.primary_key.columns.keys())
            assert actual_pk == expected_pk

            actual_indexes = {
                (index["name"], tuple(index["column_names"]), bool(index["unique"]))
                for index in inspector.get_indexes(table_name)
            }
            assert actual_indexes == EXPECTED_INDEXES[table_name]

            actual_fks = {
                (
                    fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"],
                    tuple(fk["referred_columns"]),
                )
                for fk in inspector.get_foreign_keys(table_name)
            }
            assert actual_fks == EXPECTED_FOREIGN_KEYS[table_name]

        with engine.connect() as connection:
            for table_name, expected_count in EXPECTED_SEED_COUNTS.items():
                count = connection.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar_one()
                assert count == expected_count
                assert connection.execute(text(f"SELECT * FROM `{table_name}` LIMIT 1")).first() is not None

            orphan_queries = {
                "device.dealer_id": """
                    SELECT COUNT(*) FROM device d LEFT JOIN dealer x ON x.dealer_id=d.dealer_id
                    WHERE d.dealer_id IS NOT NULL AND x.dealer_id IS NULL
                """,
                "purchase_order.dealer_id": """
                    SELECT COUNT(*) FROM purchase_order p LEFT JOIN dealer d ON d.dealer_id=p.dealer_id
                    WHERE d.dealer_id IS NULL
                """,
                "warranty_claim.device_id": """
                    SELECT COUNT(*) FROM warranty_claim w LEFT JOIN device d ON d.device_id=w.device_id
                    WHERE d.device_id IS NULL
                """,
                "warranty_claim.dealer_id": """
                    SELECT COUNT(*) FROM warranty_claim w LEFT JOIN dealer d ON d.dealer_id=w.dealer_id
                    WHERE d.dealer_id IS NULL
                """,
                "cross_region_report.device_id": """
                    SELECT COUNT(*) FROM cross_region_report r LEFT JOIN device d ON d.device_id=r.device_id
                    WHERE d.device_id IS NULL
                """,
            }
            for relation, query in orphan_queries.items():
                assert connection.execute(text(query)).scalar_one() == 0, relation

        for table_name, expected_columns in CORE_TABLE_COLUMNS.items():
            actual = tuple(column["name"] for column in inspector.get_columns(table_name))
            assert actual == expected_columns
    finally:
        engine.dispose()
