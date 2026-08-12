"""训练并评估制造业风控 XGBoost 模型。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.features import FEATURE_COLUMNS

DEFAULT_DATA = PROJECT_ROOT / "data" / "manufacturing_training_samples.csv"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "manufacturing_xgb_model.json"
DEFAULT_METRICS = PROJECT_ROOT / "models" / "training_metrics.json"


def load_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError("训练数据为空")
    features = np.asarray([[float(row[name]) for name in FEATURE_COLUMNS] for row in rows], dtype=np.float32)
    labels = np.asarray([int(row["label"]) for row in rows], dtype=np.int32)
    if len(np.unique(labels)) != 2:
        raise ValueError("训练数据必须同时包含高风险和低风险样本")
    return features, labels


def main() -> None:
    parser = argparse.ArgumentParser(description="训练制造业风控 XGBoost 模型")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()

    features, labels = load_csv(args.data)
    x_train, x_val, y_train, y_val = train_test_split(
        features, labels, test_size=0.2, random_state=args.seed, stratify=labels
    )
    positive_count = int(y_train.sum())
    negative_count = len(y_train) - positive_count
    train_matrix = xgb.DMatrix(x_train, label=y_train, feature_names=FEATURE_COLUMNS)
    validation_matrix = xgb.DMatrix(x_val, label=y_val, feature_names=FEATURE_COLUMNS)
    parameters = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": 4,
        "eta": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "min_child_weight": 2,
        "lambda": 1.5,
        "scale_pos_weight": negative_count / max(positive_count, 1),
        "seed": args.seed,
        "nthread": 2,
    }
    booster = xgb.train(
        parameters,
        train_matrix,
        num_boost_round=260,
        evals=[(validation_matrix, "validation")],
        verbose_eval=False,
    )
    probabilities = booster.predict(validation_matrix)
    predictions = (probabilities >= 0.5).astype(np.int32)
    gain_scores = booster.get_score(importance_type="gain")
    metrics = {
        "train_samples": int(len(x_train)),
        "validation_samples": int(len(x_val)),
        "positive_ratio": round(float(labels.mean()), 4),
        "val_auc": round(float(roc_auc_score(y_val, probabilities)), 4),
        "val_f1": round(float(f1_score(y_val, predictions)), 4),
        "threshold": 0.5,
        "feature_importance": {
            name: round(float(gain_scores.get(name, 0.0)), 6)
            for name in FEATURE_COLUMNS
        },
    }
    args.model.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(args.model)
    args.metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print("XGBoost 训练完成")
    print(f"训练集：{metrics['train_samples']}，验证集：{metrics['validation_samples']}，正例占比：{metrics['positive_ratio']:.2%}")
    print(f"val_auc={metrics['val_auc']:.4f}")
    print(f"val_f1={metrics['val_f1']:.4f}")
    print(f"模型：{args.model}")
    print(f"评估结果：{args.metrics}")
    top_features = sorted(metrics["feature_importance"].items(), key=lambda item: item[1], reverse=True)[:5]
    print("Top 5 特征：" + ", ".join(f"{name}={score:.4f}" for name, score in top_features))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"训练失败：{error}", file=sys.stderr)
        raise SystemExit(1) from error
