"""物流训练样本与模型产物校验。"""
import json
from pathlib import Path

from app.engine.ml_model import FEATURE_COLUMNS
from scripts.gen_business_data import SEED, build_rows


ROOT = Path(__file__).resolve().parents[1]


def test_feature_contract_has_exactly_25_unique_columns():
    assert len(FEATURE_COLUMNS) == 25
    assert len(set(FEATURE_COLUMNS)) == 25
    assert sum(name.startswith("user_") for name in FEATURE_COLUMNS) == 14
    assert sum(name.startswith("order_") for name in FEATURE_COLUMNS) == 8
    assert sum(name.startswith("addr_") for name in FEATURE_COLUMNS) == 3


def test_dataset_has_both_classes_and_adequate_positive_ratio():
    labels = [row["risk_label"] for row in build_rows(SEED)[2]]
    assert set(labels) == {0, 1}
    assert sum(labels) / len(labels) == 0.3


def test_new_xgboost_model_exists_and_is_json():
    path = ROOT / "app" / "engine" / "xgb_model.json"
    assert path.stat().st_size > 1000
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
