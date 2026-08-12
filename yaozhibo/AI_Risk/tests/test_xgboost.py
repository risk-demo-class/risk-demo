"""教育25维XGBoost接口和训练质量测试。"""
from pathlib import Path

import numpy as np

from app.engine import ml_model


def test_feature_columns_are_unique_fixed_25():
    assert len(ml_model.FEATURE_COLUMNS) == 25
    assert len(set(ml_model.FEATURE_COLUMNS)) == 25
    assert ml_model.FEATURE_COLUMNS[0] == "user_account_age_days"
    assert ml_model.FEATURE_COLUMNS[-1] == "device_id_blacklisted"


def test_features_to_array_follows_contract_order():
    arr = ml_model._features_to_array({
        "user_account_age_days": "10",
        "user_role_teacher_flag": 1,
        "device_id_blacklisted": 1,
    })
    assert arr.shape == (1, 25)
    assert arr.dtype == np.float32
    assert arr[0, 0] == 10
    assert arr[0, 1] == 1
    assert arr[0, -1] == 1


def test_probability_threshold_mapping():
    assert ml_model._prob_to_decision(0.29) == "通过"
    assert ml_model._prob_to_decision(0.30) == "标记"
    assert ml_model._prob_to_decision(0.60) == "人工审核"
    assert ml_model._prob_to_decision(0.80) == "拒绝"


def test_training_outputs_auc_f1_and_named_features(tmp_path):
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (300, 25)).astype(np.float32)
    y = np.asarray([0] * 150 + [1] * 150, dtype=np.int32)
    X[:, 0] = y * 6 + rng.normal(0, 0.2, 300)
    model_path = tmp_path / "xgb.json"
    metrics, booster = ml_model.train_and_save(
        X, y, model_path=str(model_path), num_boost_round=30,
        early_stopping_rounds=5, return_model=True,
    )
    assert metrics["val_auc"] >= 0.9
    assert metrics["val_f1"] >= 0.9
    assert model_path.exists()
    assert booster.feature_names == ml_model.FEATURE_COLUMNS
    assert ml_model.load_model(str(model_path)) is True


def test_missing_or_stale_model_falls_back_safely(tmp_path):
    assert ml_model.load_model(str(tmp_path / "missing.json")) is False
    result = ml_model.predict({})
    assert result.is_loaded is False
    assert result.score == 0
