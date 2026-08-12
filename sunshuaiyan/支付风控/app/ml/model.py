from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

from app.config import ROOT, get_settings
from app.services.features import INBOUND_FEATURE_COLUMNS


@lru_cache(maxsize=1)
def load_model_bundle() -> tuple[xgb.XGBClassifier | None, dict[str, Any]]:
    settings = get_settings()
    metrics_path = ROOT / "artifacts" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    if not settings.model_path.exists():
        return None, metrics
    model = xgb.XGBClassifier()
    model.load_model(settings.model_path)
    return model, metrics


def predict_probability(features: dict[str, Any]) -> tuple[float, bool]:
    model, _ = load_model_bundle()
    if model is None:
        return 0.0, False
    row = np.asarray(
        [[float(features.get(name) or 0.0) for name in INBOUND_FEATURE_COLUMNS]],
        dtype=np.float32,
    )
    return float(model.predict_proba(row)[0, 1]), True


def model_metrics() -> dict[str, Any]:
    _, metrics = load_model_bundle()
    return metrics


def clear_model_cache() -> None:
    load_model_bundle.cache_clear()
