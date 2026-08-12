"""XGBoost 模型工具测试."""

import numpy as np

from app.engine.feature_registry import FEATURE_COLUMNS
from app.engine.ml_model import _features_to_array, _prob_to_risk_score


def test_features_to_array_length():
    array = _features_to_array({})
    assert array.shape == (1, len(FEATURE_COLUMNS))
    assert np.isfinite(array).all()


def test_prob_to_risk_score():
    assert _prob_to_risk_score(0) == 0.0
    assert _prob_to_risk_score(1) == 100.0
    assert 0 < _prob_to_risk_score(0.5) < 100
