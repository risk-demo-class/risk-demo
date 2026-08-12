"""Load, calibrate and score the five scenario-specific XGBoost models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import exp, log
from pathlib import Path
from typing import Any

import numpy as np
from xgboost import XGBClassifier

from app.config import settings
from app.engine.model_specs import MODEL_SPECS, SCENARIO_MODELS, vectorize


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    score: int
    probability: float
    version: str
    submodels: dict[str, float]


def _calibrated_probability(probability: float, coefficient: float, intercept: float) -> float:
    clipped = min(1 - 1e-5, max(1e-5, probability))
    calibrated = 1.0 / (1.0 + exp(-(coefficient * log(clipped / (1 - clipped)) + intercept)))
    return min(1.0, max(0.0, calibrated))


class ModelManager:
    def __init__(self) -> None:
        self._models: dict[str, XGBClassifier] = {}
        self._registry: dict[str, Any] = {}

    @property
    def model_dir(self) -> Path:
        return Path(settings.MODEL_DIR)

    def ensure_ready(self) -> bool:
        registry_path = self.model_dir / "registry.json"
        missing = [spec.artifact for spec in MODEL_SPECS.values() if not (self.model_dir / spec.artifact).exists()]
        if (not registry_path.exists() or missing) and settings.MODEL_AUTO_TRAIN:
            from app.engine.model_training import train_all

            train_all(self.model_dir)
        if not registry_path.exists():
            return False
        self._registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for name, spec in MODEL_SPECS.items():
            artifact = self.model_dir / spec.artifact
            if not artifact.exists():
                continue
            model = XGBClassifier()
            model.load_model(artifact)
            self._models[name] = model
        return len(self._models) == len(MODEL_SPECS)

    def status(self) -> dict[str, dict[str, Any]]:
        models = self._registry.get("models", {})
        return {
            name: {
                "ready": name in self._models,
                "artifact": spec.artifact,
                "metrics": models.get(name, {}).get("metrics"),
                "version": models.get(name, {}).get("version"),
            }
            for name, spec in MODEL_SPECS.items()
        }

    def score(self, scenario: str, features: dict[str, Any]) -> ModelEvaluation | None:
        model_names = SCENARIO_MODELS.get(scenario, ())
        if not model_names or any(name not in self._models for name in model_names):
            return None
        submodels: dict[str, float] = {}
        versions: set[str] = set()
        registry_models = self._registry.get("models", {})
        for name in model_names:
            spec = MODEL_SPECS[name]
            vector = np.asarray([vectorize(spec, features)], dtype=np.float32)
            raw_probability = float(self._models[name].predict_proba(vector)[0, 1])
            metadata = registry_models[name]
            calibration = metadata["calibration"]
            probability = _calibrated_probability(
                raw_probability,
                float(calibration["coefficient"]),
                float(calibration["intercept"]),
            )
            submodels[name] = round(probability, 6)
            versions.add(metadata["version"])
        final_probability = max(submodels.values())
        return ModelEvaluation(
            score=min(100, round(final_probability * 100)),
            probability=final_probability,
            version="+".join(sorted(versions)),
            submodels=submodels,
        )


model_manager = ModelManager()
