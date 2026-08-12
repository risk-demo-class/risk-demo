"""XGBoost 模型单测: 特征对齐 / 推理兜底 / 小样本训练"""
import numpy as np
import pytest

from app.engine import ml_model
from app.engine.ml_model import (
    FEATURE_COLUMNS,
    _features_to_array,
    _prob_to_decision,
    predict,
    train_and_save,
)


def test_feature_columns_count_28():
    assert len(FEATURE_COLUMNS) == 28


def test_features_to_array_missing_zero_fill():
    arr = _features_to_array({})
    assert arr.shape == (1, 28)
    assert arr[0].sum() == 0


def test_features_to_array_order_stable():
    feats = {col: float(i) for i, col in enumerate(FEATURE_COLUMNS)}
    arr = _features_to_array(feats)
    assert arr[0, 0] == 0.0
    assert arr[0, 27] == 27.0


def test_prob_to_decision_thresholds():
    assert _prob_to_decision(0.1) == "通过"
    assert _prob_to_decision(0.5) == "标记"
    assert _prob_to_decision(0.7) == "人工审核"
    assert _prob_to_decision(0.9) == "拒绝"


def test_predict_fallback_when_not_loaded():
    ml_model._LOADED = False
    ml_model._MODEL = None
    result = predict({col: 0.0 for col in FEATURE_COLUMNS})
    assert result.score == 0.0
    assert result.decision == "通过"
    assert result.is_loaded is False


def test_train_and_save_small(tmp_path):
    """小样本训练必须能跑通并保存模型."""
    rng = np.random.default_rng(0)
    n = 60
    X = rng.uniform(0, 1, size=(n, 28)).astype(np.float32)
    # 制造正负样本模式
    y = ((X[:, 0] > 0.5) & (X[:, 1] > 0.5)).astype(np.int32)
    if y.sum() == 0:
        y[:10] = 1
    path = str(tmp_path / "test_model.json")
    metrics = train_and_save(
        X, y, model_path=path, num_boost_round=10,
        early_stopping_rounds=None,
    )
    assert metrics["n_samples"] == n
    assert metrics["n_pos"] >= 1
    assert metrics["best_iter"] >= 1
    import os
    assert os.path.exists(path)
