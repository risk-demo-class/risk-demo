import ast
from pathlib import Path

import xgboost as xgb

from app.database import Base
import app.models  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]

BUSINESS_TABLES = {
    "user_info", "bank_card", "bank_transaction", "loan_application",
    "login_log", "device_fingerprint", "ip_geo_location", "blacklist_extra",
}
RISK_TABLES = {
    "risk_rule", "risk_event", "risk_feature", "risk_assessment", "risk_case",
    "risk_blacklist", "risk_user_profile", "risk_action_log", "risk_alert",
}


def _feature_columns():
    tree = ast.parse((ROOT / "app/engine/ml_model.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "FEATURE_COLUMNS":
            return ast.literal_eval(node.value)
    raise AssertionError("FEATURE_COLUMNS not found")


def test_exactly_8_business_plus_9_risk_tables():
    names = set(Base.metadata.tables)
    assert BUSINESS_TABLES <= names
    assert RISK_TABLES <= names
    assert len(BUSINESS_TABLES | RISK_TABLES) == 17


def test_25_feature_contract_and_families():
    columns = _feature_columns()
    assert len(columns) == len(set(columns)) == 25
    assert sum(name.startswith("user_") for name in columns) == 10
    assert sum(name.startswith("event_") for name in columns) == 10
    assert sum(name.startswith("context_") for name in columns) == 5


def test_packaged_xgboost_model_uses_25_features():
    model = xgb.Booster()
    model.load_model(str(ROOT / "app/engine/xgb_model.json"))
    assert model.num_features() == 25
