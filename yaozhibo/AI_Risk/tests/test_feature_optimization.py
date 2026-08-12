"""教育版特征契约测试：防止规则、特征工程和模型列再次错位。"""
from pathlib import Path
import re

import numpy as np

from app.engine import ml_model


ROOT = Path(__file__).resolve().parents[1]


def _rule_fields() -> set[str]:
    sql = (ROOT / "sql" / "init_risk_data.sql").read_text(encoding="utf-8")
    return set(re.findall(r'"field"\s*:\s*"([a-z0-9_]+)"', sql))


def test_feature_contract_is_fixed_25_dimensions():
    assert len(ml_model.FEATURE_COLUMNS) == 25
    assert len(set(ml_model.FEATURE_COLUMNS)) == 25


def test_rule_fields_are_model_features():
    fields = _rule_fields()
    assert fields
    assert fields <= set(ml_model.FEATURE_COLUMNS)


def test_feature_source_declares_every_model_feature():
    source = (ROOT / "app" / "engine" / "feature.py").read_text(encoding="utf-8")
    missing = [name for name in ml_model.FEATURE_COLUMNS if f'"{name}"' not in source]
    assert missing == []


def test_features_to_array_uses_contract_order_and_zero_fallback():
    first = ml_model.FEATURE_COLUMNS[0]
    last = ml_model.FEATURE_COLUMNS[-1]
    arr = ml_model._features_to_array({first: "12.5", last: 1})
    assert arr.shape == (1, 25)
    assert arr.dtype == np.float32
    assert arr[0, 0] == 12.5
    assert np.all(arr[0, 1:-1] == 0)
    assert arr[0, -1] == 1
