"""Deterministic synthetic training pipeline for five demonstration models.

Synthetic labels come from independent latent-risk functions plus random noise;
they are not copied from rule decisions. Replace this generator with governed
bank labels before production use.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

from app.engine.model_specs import MODEL_SPECS, ModelSpec


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -30, 30)))


def _common(rng: np.random.Generator, size: int) -> dict[str, np.ndarray]:
    return {
        "amount": np.clip(rng.lognormal(8.4, 1.15, size), 10, 200000),
        "event_hour": rng.integers(0, 24, size),
        "transactions_1h": np.clip(rng.poisson(1.2, size) + 1, 1, 12),
        "distinct_from_cards_1h": np.clip(rng.poisson(0.7, size) + 1, 1, 10),
        "device_age_days": np.clip(rng.exponential(100, size), 0, 730),
        "device_user_count": np.clip(rng.poisson(0.8, size) + 1, 1, 15),
        "is_proxy": rng.binomial(1, 0.08, size),
        "is_tor": rng.binomial(1, 0.025, size),
        "beneficiary_blacklisted": rng.binomial(1, 0.025, size),
        "city_mismatch": rng.binomial(1, 0.18, size),
        "credit_score": np.clip(rng.normal(650, 75, size), 300, 850),
        "term_months": rng.choice([6, 12, 24, 36, 60], size=size),
        "monthly_income": np.clip(rng.lognormal(9.2, 0.55, size), 2500, 100000),
        "debt_ratio": np.clip(rng.beta(2.2, 4.5, size), 0.01, 0.98),
        "loan_institution_count_month": np.clip(rng.poisson(0.8, size) + 1, 1, 8),
        "login_failed": rng.binomial(1, 0.14, size),
    }


def generate_dataset(spec: ModelSpec, size: int = 3000, seed: int = 20260811) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed + sum(ord(char) for char in spec.name))
    values = _common(rng, size)
    night = ((values["event_hour"] <= 5) | (values["event_hour"] >= 23)).astype(float)
    if spec.name == "CARD":
        latent = (-3.5 + values["amount"] / 30000 + night * 1.2 + np.maximum(values["transactions_1h"] - 2, 0) * 0.75 + (values["device_age_days"] < 7) * 1.4 + (values["device_user_count"] >= 5) * 1.8 + values["is_proxy"] * 1.5 - (values["credit_score"] - 650) / 130)
    elif spec.name == "TRANSFER":
        latent = (-4.0 + values["amount"] / 25000 + night * 1.0 + np.maximum(values["distinct_from_cards_1h"] - 2, 0) * 1.2 + values["city_mismatch"] * 1.5 + values["beneficiary_blacklisted"] * 5.0 + values["is_proxy"] * 1.3 + (values["device_age_days"] < 7) * 1.2)
    elif spec.name == "LOAN_DEFAULT":
        payment_pressure = values["amount"] / np.maximum(values["monthly_income"] * values["term_months"], 1)
        latent = (-3.2 + values["debt_ratio"] * 5.0 + payment_pressure * 4.0 - (values["credit_score"] - 620) / 80 + (values["term_months"] >= 36) * 0.55)
    elif spec.name == "LOAN_FRAUD":
        latent = (-3.8 + np.maximum(values["loan_institution_count_month"] - 1, 0) * 1.1 + (values["device_age_days"] < 7) * 1.5 + (values["device_user_count"] >= 5) * 2.0 + values["is_proxy"] * 1.5 - (values["credit_score"] - 620) / 170 + values["amount"] / 60000)
    else:
        latent = (-3.6 + night * 1.2 + (values["device_age_days"] < 3) * 1.5 + np.maximum(values["device_user_count"] - 2, 0) * 0.65 + values["is_proxy"] * 1.8 + values["is_tor"] * 3.0 + values["login_failed"] * 1.2)
    latent += rng.normal(0, 0.35, size)
    labels = rng.binomial(1, _sigmoid(latent)).astype(np.int32)
    matrix = np.column_stack([values[name] for name in spec.features]).astype(np.float32)
    return matrix, labels


def _calibrate(probabilities: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    clipped = np.clip(probabilities, 1e-5, 1 - 1e-5)
    logits = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, solver="lbfgs")
    calibrator.fit(logits, labels)
    return float(calibrator.coef_[0, 0]), float(calibrator.intercept_[0])


def apply_calibration(probabilities: np.ndarray, coefficient: float, intercept: float) -> np.ndarray:
    clipped = np.clip(probabilities, 1e-5, 1 - 1e-5)
    logits = np.log(clipped / (1 - clipped))
    return _sigmoid(coefficient * logits + intercept)


def train_one(spec: ModelSpec, output_dir: Path, size: int = 3000) -> dict:
    matrix, labels = generate_dataset(spec, size=size)
    train_end = int(size * 0.7)
    calibration_end = int(size * 0.85)
    train_x, train_y = matrix[:train_end], labels[:train_end]
    calibration_x, calibration_y = matrix[train_end:calibration_end], labels[train_end:calibration_end]
    test_x, test_y = matrix[calibration_end:], labels[calibration_end:]
    model = XGBClassifier(
        n_estimators=90,
        max_depth=3,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=4,
        reg_lambda=2.0,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=20260811,
        n_jobs=2,
    )
    model.fit(train_x, train_y)
    calibration_prob = model.predict_proba(calibration_x)[:, 1]
    coefficient, intercept = _calibrate(calibration_prob, calibration_y)
    raw_test_prob = model.predict_proba(test_x)[:, 1]
    test_prob = apply_calibration(raw_test_prob, coefficient, intercept)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / spec.artifact
    model.save_model(artifact_path)
    return {
        "name": spec.name,
        "scenario": spec.scenario,
        "artifact": spec.artifact,
        "features": list(spec.features),
        "version": "xgb-synthetic-v1",
        "training_source": "independent_synthetic_latent_labels",
        "sample_size": size,
        "positive_rate": round(float(labels.mean()), 6),
        "calibration": {"coefficient": coefficient, "intercept": intercept, "method": "platt"},
        "metrics": {
            "roc_auc": round(float(roc_auc_score(test_y, test_prob)), 6),
            "pr_auc": round(float(average_precision_score(test_y, test_prob)), 6),
            "brier": round(float(brier_score_loss(test_y, test_prob)), 6),
        },
        "trained_at": datetime.now(UTC).isoformat(),
    }


def train_all(output_dir: str | Path, size: int = 3000) -> dict:
    target = Path(output_dir)
    models = {name: train_one(spec, target, size=size) for name, spec in MODEL_SPECS.items()}
    registry = {"version": "bankrisk-model-registry-v1", "models": models}
    (target / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return registry
