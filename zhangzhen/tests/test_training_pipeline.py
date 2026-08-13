"""训练纯度、时间切分、指标、模型保存加载与降级测试。"""

from datetime import datetime, timedelta

from app.config import settings
from app.engine.feature import FEATURE_COLUMNS
from app.engine.ml_model import XGBoostRiskModel
from app.engine.training import (
    TrainingSample,
    train_xgboost_model,
    validate_training_samples,
)


def _samples(count: int = 160) -> list[TrainingSample]:
    start = datetime(2026, 1, 1)
    values = []
    for index in range(count):
        label = int(index % 4 == 0)
        features = [0.0] * len(FEATURE_COLUMNS)
        features[FEATURE_COLUMNS.index("txn_amount")] = 60_000.0 if label else 800.0
        features[FEATURE_COLUMNS.index("txn_cross_city")] = float(label)
        features[FEATURE_COLUMNS.index("user_credit_score")] = 520.0 if label else 720.0
        values.append(
            TrainingSample(
                assessment_id=f"A{index}", event_id=f"E{index}", user_id=f"U{index}",
                event_time=start + timedelta(hours=index * 12),
                features=tuple(features), label=label,
            )
        )
    return values


def test_validate_training_samples_checks_25_dimensions_and_span():
    report = validate_training_samples(
        _samples(), min_samples=100, min_span_days=30
    )
    assert report.samples == 160
    assert report.feature_count == 25
    assert report.positive_ratio == 0.25
    assert report.span_days >= 30


def test_xgboost_train_save_reload_and_missing_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "XGB_ENABLED", True)
    model_path = tmp_path / "xgb_model.json"
    metrics = train_xgboost_model(
        _samples(), model_path=model_path, rounds=60, early_stopping_rounds=8
    )
    assert model_path.exists()
    assert model_path.with_suffix(".metrics.json").exists()
    assert metrics.feature_count == 25
    assert metrics.validation_auc >= 0.70
    assert metrics.validation_f1 >= 0.50

    model = XGBoostRiskModel(model_path)
    assert model.load() is True
    sample = dict(zip(FEATURE_COLUMNS, _samples()[0].features, strict=True))
    probability = model.predict(sample)
    assert probability is not None and 0 <= probability <= 1

    missing = XGBoostRiskModel(tmp_path / "missing.json")
    assert missing.predict(sample) is None
