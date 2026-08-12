from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import engine  # noqa: E402
from app.services.features import INBOUND_FEATURE_COLUMNS, load_inbound_dataset  # noqa: E402


def best_threshold(y_true: np.ndarray, probabilities: np.ndarray) -> tuple[float, float]:
    candidates = np.linspace(0.10, 0.90, 161)
    scored = [(float(t), f1_score(y_true, probabilities >= t)) for t in candidates]
    return max(scored, key=lambda item: item[1])


def train(output_dir: Path) -> dict:
    frame = load_inbound_dataset(engine, labeled_only=True).sort_values(["received_at", "inbound_payment_id"])
    if len(frame) < 100:
        raise RuntimeError(f"training requires at least 100 labeled rows, got {len(frame)}")
    n = len(frame)
    train_end = int(n * 0.70)
    calibration_end = int(n * 0.85)
    train_df = frame.iloc[:train_end]
    calibration_df = frame.iloc[train_end:calibration_end]
    validation_df = frame.iloc[calibration_end:]

    x_train = train_df[INBOUND_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_train = train_df["label"].to_numpy(dtype=np.int32)
    x_cal = calibration_df[INBOUND_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_cal = calibration_df["label"].to_numpy(dtype=np.int32)
    x_val = validation_df[INBOUND_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_val = validation_df["label"].to_numpy(dtype=np.int32)

    positives = int(y_train.sum())
    negatives = len(y_train) - positives
    scale_pos_weight = min(10.0, negatives / max(1, positives))
    model = xgb.XGBClassifier(
        objective="binary:logistic",
        n_estimators=350,
        max_depth=4,
        learning_rate=0.035,
        min_child_weight=3,
        subsample=0.85,
        colsample_bytree=0.82,
        reg_alpha=0.15,
        reg_lambda=1.5,
        scale_pos_weight=scale_pos_weight,
        eval_metric="auc",
        random_state=20260811,
        n_jobs=max(1, min(6, os.cpu_count() or 2)),
    )
    model.fit(x_train, y_train, eval_set=[(x_cal, y_cal)], verbose=False)
    calibration_prob = model.predict_proba(x_cal)[:, 1]
    threshold, calibration_f1 = best_threshold(y_cal, calibration_prob)
    val_prob = model.predict_proba(x_val)[:, 1]
    val_pred = (val_prob >= threshold).astype(np.int32)
    val_auc = roc_auc_score(y_val, val_prob)
    val_f1 = f1_score(y_val, val_pred)
    cm = confusion_matrix(y_val, val_pred, labels=[0, 1])

    importances = sorted(
        zip(INBOUND_FEATURE_COLUMNS, model.feature_importances_.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )
    metrics = {
        "model_type": "XGBoost binary classifier",
        "model_version": "pingpong-inbound-xgb-1.0.0",
        "label_definition": "1=REJECTED/REFUNDED, 0=APPROVED; synthetic weak-supervision outcome label",
        "split_strategy": "70% train, 15% threshold calibration, 15% untouched temporal validation",
        "feature_count": len(INBOUND_FEATURE_COLUMNS),
        "dataset_rows": n,
        "train_rows": len(train_df),
        "calibration_rows": len(calibration_df),
        "validation_rows": len(validation_df),
        "positive_rate": round(float(frame["label"].mean()), 6),
        "scale_pos_weight": round(float(scale_pos_weight), 6),
        "threshold": round(float(threshold), 4),
        "calibration_f1": round(float(calibration_f1), 6),
        "val_auc": round(float(val_auc), 6),
        "val_f1": round(float(val_f1), 6),
        "val_precision": round(float(precision_score(y_val, val_pred, zero_division=0)), 6),
        "val_recall": round(float(recall_score(y_val, val_pred, zero_division=0)), 6),
        "confusion_matrix": {
            "tn": int(cm[0, 0]),
            "fp": int(cm[0, 1]),
            "fn": int(cm[1, 0]),
            "tp": int(cm[1, 1]),
        },
        "top_features": [
            {"name": name, "importance": round(float(value), 6)}
            for name, value in importances[:15]
        ],
        "feature_columns": INBOUND_FEATURE_COLUMNS,
        "validation_window": {
            "from": str(validation_df["received_at"].min()),
            "to": str(validation_df["received_at"].max()),
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(output_dir / "xgb_inbound_model.json")
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    frame[["inbound_payment_id", "transaction_id", "received_at", "label"]].to_csv(
        output_dir / "training_manifest.csv", index=False
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    print(json.dumps(train(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
