import app.models  # noqa: F401
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.database import Base


def test_complete_project_has_eight_business_and_ten_risk_tables() -> None:
    expected = {
        "user_info",
        "bank_card",
        "bank_transaction",
        "loan_application",
        "login_log",
        "device_fingerprint",
        "ip_geo_location",
        "blacklist_extra",
        "risk_rule",
        "risk_event",
        "risk_feature_snapshot",
        "risk_rule_hit",
        "risk_assessment",
        "risk_label",
        "risk_case",
        "risk_appeal",
        "risk_appeal_evidence",
        "risk_action_log",
    }
    assert set(Base.metadata.tables) == expected


def test_independent_label_does_not_reference_assessment_decision() -> None:
    columns = set(Base.metadata.tables["risk_label"].columns.keys())
    assert "label" in columns
    assert "label_source" in columns
    assert "assessment_id" not in columns


def test_all_tables_compile_for_mysql_8() -> None:
    dialect = mysql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "CREATE TABLE" in ddl
