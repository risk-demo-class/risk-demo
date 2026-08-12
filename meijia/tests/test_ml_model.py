"""ML 轨道单测: 特征数组对齐、概率→决策、兜底、训练保存。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.engine import ml_model
from app.engine.ml_model import (
    _features_to_array, _prob_to_decision, predict, train_and_save,
)
from app.engine.feature import compute_all_features
from app.engine.feature import ACCOUNT_FEATURES, BEHAVIOR_FEATURES, ENROLLMENT_FEATURES


def test_feature_columns_align_with_feature_module():
    # 特征顺序必须与 feature.py 完全一致, 否则训练/推理特征错位
    assert ml_model.FEATURE_COLUMNS == list(ACCOUNT_FEATURES) + list(ENROLLMENT_FEATURES) + list(BEHAVIOR_FEATURES)


def test_features_to_array_ordering_and_fallback():
    partial = {ml_model.FEATURE_COLUMNS[0]: 1.0, ml_model.FEATURE_COLUMNS[1]: "x", "unknown": 9.0}
    arr = _features_to_array(partial)
    assert arr.shape == (1, 25)
    assert arr[0, 0] == 1.0        # 已知值
    assert arr[0, 1] == 0.0        # 非数值 → 0 兜底
    assert arr[0, 2] == 0.0        # 缺失 → 0


def test_prob_to_decision_default_thresholds():
    assert _prob_to_decision(0.1) == "通过"
    assert _prob_to_decision(0.45) == "标记"
    assert _prob_to_decision(0.7) == "人工审核"
    assert _prob_to_decision(0.95) == "拒绝"


def test_predict_fallback_when_not_loaded():
    ml_model._MODEL = None
    ml_model._LOADED = False
    result = predict({})
    assert result.is_loaded is False
    assert result.score == 0.0
    assert result.decision == "通过"


def test_train_and_save_smoke(tmp_path):
    rng = np.random.default_rng(7)
    n = 200
    X = rng.normal(size=(n, 25)).astype(np.float32)
    # 让前 25 维的可分性决定标签
    y = (np.sum(X[:, :5], axis=1) > 0).astype(np.int32)
    # 保证正负都存在
    if not (y.min() == 0 and y.max() == 1):
        y[0] = 0
        y[1] = 1
    target = str(tmp_path / "model.json")
    metrics, booster = train_and_save(
        X, y, model_path=target, num_boost_round=20,
        early_stopping_rounds=None, return_model=True,
    )
    assert (tmp_path / "model.json").exists()
    assert booster is not None
    assert set(["n", "n_pos", "n_neg", "pos_ratio", "accuracy", "f1"]) <= set(metrics)
    assert 0 < metrics["n_pos"] < n
    # 可分数据应达到不错的准确率
    assert metrics["accuracy"] >= 0.5
