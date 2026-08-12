from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_xgboost_artifacts_and_validation_metrics() -> None:
    model_path = ROOT / "artifacts" / "xgb_inbound_model.json"
    metrics_path = ROOT / "artifacts" / "metrics.json"
    manifest_path = ROOT / "artifacts" / "training_manifest.csv"

    assert model_path.stat().st_size > 0
    assert manifest_path.stat().st_size > 0
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert metrics["model_type"] == "XGBoost binary classifier"
    assert metrics["feature_count"] == 41
    assert 0.5 <= metrics["val_auc"] <= 1
    assert 0 < metrics["val_f1"] <= 1
    assert metrics["validation_rows"] > 0
    assert sum(metrics["confusion_matrix"].values()) == metrics["validation_rows"]
