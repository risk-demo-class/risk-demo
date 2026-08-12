"""Train the manufacturing XGBoost model with dealer-group isolation."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS
from scripts.ml_pipeline_common import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    SnapshotDataset,
    load_dataset,
    vector_hashes,
)

logger = logging.getLogger(__name__)


def group_split(
    dataset: SnapshotDataset,
    *,
    test_size: float | None = None,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | float]]:
    """Choose a dealer-disjoint split containing both labels on both sides."""
    size = settings.XGB_TEST_SIZE if test_size is None else test_size
    global_ratio = float(dataset.y.mean())
    splitter = GroupShuffleSplit(n_splits=64, test_size=size, random_state=random_state)
    candidates = []
    for train_idx, val_idx in splitter.split(dataset.X, dataset.y, dataset.groups):
        if len(np.unique(dataset.y[train_idx])) < 2 or len(np.unique(dataset.y[val_idx])) < 2:
            continue
        score = abs(float(dataset.y[train_idx].mean()) - global_ratio)
        score += abs(float(dataset.y[val_idx].mean()) - global_ratio)
        candidates.append((score, train_idx, val_idx))
    if not candidates:
        raise RuntimeError("unable to create a dealer-group split containing both labels")
    _, train_idx, val_idx = min(candidates, key=lambda item: item[0])

    train_groups = set(dataset.groups[train_idx])
    val_groups = set(dataset.groups[val_idx])
    train_sources = set(dataset.source_ids[train_idx])
    val_sources = set(dataset.source_ids[val_idx])
    duplicate_vectors = vector_hashes(dataset.X[train_idx]) & vector_hashes(dataset.X[val_idx])
    audit = {
        "train_dealers": len(train_groups),
        "validation_dealers": len(val_groups),
        "dealer_overlap": len(train_groups & val_groups),
        "source_overlap": len(train_sources & val_sources),
        "exact_feature_vector_overlap": len(duplicate_vectors),
    }
    if audit["dealer_overlap"] or audit["source_overlap"]:
        raise RuntimeError(f"group leakage detected: {audit}")
    return train_idx, val_idx, audit


def train_model(
    dataset: SnapshotDataset,
    *,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    num_boost_round: int = 300,
) -> tuple[xgb.Booster, dict]:
    if len(FEATURE_COLUMNS) != 25:
        raise RuntimeError("online FEATURE_COLUMNS contract is not 25-dimensional")
    if dataset.X.shape[1] != 25 or not np.isfinite(dataset.X).all():
        raise RuntimeError(f"training matrix must be finite (N,25), got {dataset.X.shape}")

    train_idx, val_idx, leakage = group_split(dataset)
    X_train, X_val = dataset.X[train_idx], dataset.X[val_idx]
    y_train, y_val = dataset.y[train_idx], dataset.y[val_idx]
    positive = int(y_train.sum())
    negative = int(len(y_train) - positive)
    scale_pos_weight = min(
        negative / positive if positive else 1.0,
        settings.XGB_MAX_SCALE_POS_WEIGHT,
    )

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_COLUMNS)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", settings.XGB_EARLY_STOP_METRIC],
        "max_depth": settings.XGB_MAX_DEPTH,
        "eta": settings.XGB_LEARNING_RATE,
        "min_child_weight": settings.XGB_MIN_CHILD_WEIGHT,
        "reg_alpha": settings.XGB_REG_ALPHA,
        "reg_lambda": settings.XGB_REG_LAMBDA,
        "gamma": settings.XGB_GAMMA,
        "subsample": settings.XGB_SUBSAMPLE,
        "colsample_bytree": settings.XGB_COLSAMPLE_BYTREE,
        "scale_pos_weight": scale_pos_weight,
        "tree_method": "hist",
        "seed": 42,
        "verbosity": 0,
    }
    # AUC can reach 1.0 as soon as the weak-rule labels are ranked correctly,
    # while probabilities are still close to 0.5. Keep the project's configured
    # warmup phase so online probability thresholds are meaningfully calibrated.
    warmup_rounds = min(settings.XGB_WARMUP_ROUNDS, max(1, num_boost_round // 2))
    warmup_params = {**params, "eval_metric": "logloss"}
    warmup_model = xgb.train(
        warmup_params,
        dtrain,
        num_boost_round=warmup_rounds,
        evals=[(dtrain, "train"), (dval, "validation")],
        verbose_eval=False,
    )
    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=max(1, num_boost_round - warmup_rounds),
        evals=[(dtrain, "train"), (dval, "validation")],
        early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        xgb_model=warmup_model,
        verbose_eval=False,
    )
    probabilities = booster.predict(dval)
    predictions = (probabilities >= 0.5).astype(np.int8)
    matrix = confusion_matrix(y_val, predictions, labels=[0, 1])
    metrics = {
        "training_samples": int(len(train_idx)),
        "validation_samples": int(len(val_idx)),
        "training_label_0": int(np.sum(y_train == 0)),
        "training_label_1": int(np.sum(y_train == 1)),
        "validation_label_0": int(np.sum(y_val == 0)),
        "validation_label_1": int(np.sum(y_val == 1)),
        "accuracy": round(float(accuracy_score(y_val, predictions)), 6),
        "precision": round(float(precision_score(y_val, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(y_val, predictions, zero_division=0)), 6),
        "f1": round(float(f1_score(y_val, predictions, zero_division=0)), 6),
        "roc_auc": round(float(roc_auc_score(y_val, probabilities)), 6),
        "confusion_matrix": matrix.tolist(),
        "best_iteration": int(getattr(booster, "best_iteration", num_boost_round - 1)),
        "scale_pos_weight": round(scale_pos_weight, 6),
        "warmup_rounds": warmup_rounds,
        "feature_count": int(booster.num_features()),
        "leakage_audit": leakage,
        "parameters": params,
    }
    metrics["near_perfect_score_warning"] = bool(
        metrics["accuracy"] >= 0.98 or metrics["roc_auc"] >= 0.98
    )
    metrics["score_interpretation"] = (
        "规则弱监督标签；高分表示模型较好地模仿当前规则，不代表真实欺诈检测能力"
    )

    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(path)
    if booster.num_features() != 25 or booster.feature_names != FEATURE_COLUMNS:
        raise RuntimeError("saved model feature contract differs from FEATURE_COLUMNS")
    metrics_path = path.with_suffix(path.suffix + ".metrics.json")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics["model_path"] = str(path)
    metrics["metrics_path"] = str(metrics_path)
    return booster, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="按 dealer_id 分组切分并训练制造业 XGBoost")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--num-boost-round", type=int, default=300)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dataset = load_dataset(args.dataset)
    _, metrics = train_model(
        dataset, model_path=args.model_path, num_boost_round=args.num_boost_round,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
