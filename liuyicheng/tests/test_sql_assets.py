import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _feature_columns():
    tree = ast.parse((ROOT / "app/engine/ml_model.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "FEATURE_COLUMNS":
            return set(ast.literal_eval(node.value))
    raise AssertionError("FEATURE_COLUMNS not found")


def test_business_ddl_has_eight_bank_tables_only():
    sql = (ROOT / "sql/init_business_tables.sql").read_text(encoding="utf-8")
    tables = re.findall(r"CREATE TABLE(?: IF NOT EXISTS)?\s+`?([a-z_]+)`?", sql, re.I)
    assert set(tables) == {
        "user_info", "bank_card", "bank_transaction", "loan_application",
        "login_log", "device_fingerprint", "ip_geo_location", "blacklist_extra",
    }


def test_initial_dataset_has_more_than_100_rows_and_risk_samples():
    sql = (ROOT / "sql/init_business_data.sql").read_text(encoding="utf-8")
    assert len(re.findall(r"^\('", sql, re.M)) >= 100
    for source_id in ["TXN_GEO_001", "TXN_BLACK_CARD", "LOAN_MULTI_1", "LOGIN_PROXY"]:
        assert source_id in sql
    assert "C_BLACK" in sql
    assert len(re.findall(r"'[0-9a-f]{64}'", sql)) >= 30
    assert "IDHASH" not in sql and "CARDHASH" not in sql and "EXTRAHASH" not in sql


def test_twelve_rules_only_reference_online_features():
    sql = (ROOT / "sql/init_risk_data.sql").read_text(encoding="utf-8")
    rule_ids = re.findall(r"\('(R\d{3})'", sql)
    assert len(rule_ids) == len(set(rule_ids)) == 12
    for required in ["R001", "R002", "R005", "R008", "R012", "R018", "R025", "R030"]:
        assert required in rule_ids
    fields = set(re.findall(r'"field":"([a-z0-9_]+)"', sql))
    assert fields <= _feature_columns()
