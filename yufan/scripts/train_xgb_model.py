"""从教育风控 CSV 训练 XGBoost，并保存模型和指标 JSON。"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FEATURE_COLUMNS + ["label"]:
            raise ValueError("CSV 列顺序必须与 FEATURE_COLUMNS 完全一致，并以 label 结尾")
        rows = list(reader)
    if not rows:
        raise ValueError("训练集为空")
    X = np.asarray(
        [[float(row[name]) for name in FEATURE_COLUMNS] for row in rows], dtype=np.float32
    )
    y = np.asarray([int(row["label"]) for row in rows], dtype=np.int32)
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("训练集必须同时包含正例 label=1 和负例 label=0")
    return X, y


def main() -> None:
    parser = argparse.ArgumentParser(description="训练教育行业 XGBoost 风控模型")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data" / "education_train_dataset.csv")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "app" / "engine" / "xgb_model.json")
    parser.add_argument("--metrics", type=Path, default=PROJECT_ROOT / "data" / "education_model_metrics.json")
    args = parser.parse_args()

    X, y = load_csv(args.dataset)
    logger.info("教育训练矩阵: X=%s, 正例=%d (%.1f%%)", X.shape, int(y.sum()), 100 * y.mean())
    metrics, model = train_and_save(
        X,
        y,
        model_path=str(args.model),
        num_boost_round=200,
        early_stopping_rounds=20,
        return_model=True,
    )
    importance = model.get_score(importance_type="gain") if model is not None else {}
    top_features = sorted(importance.items(), key=lambda item: item[1], reverse=True)[:10]
    report = {
        "industry": "教育风控",
        "dataset": str(args.dataset.relative_to(PROJECT_ROOT)),
        "feature_count": len(FEATURE_COLUMNS),
        "sample_count": int(len(y)),
        "positive_count": int(y.sum()),
        "negative_count": int(len(y) - y.sum()),
        "val_auc": metrics.get("val_auc"),
        "val_f1": metrics.get("val_f1"),
        "val_accuracy": metrics.get("val_accuracy"),
        "best_iteration": metrics.get("best_iteration"),
        "best_f1_threshold": metrics.get("best_f1_threshold"),
        "model_path": str(args.model.relative_to(PROJECT_ROOT)),
        "top_features": [{"name": name, "gain": round(float(gain), 4)} for name, gain in top_features],
    }
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("val_auc=%.4f, val_f1=%.4f", report["val_auc"], report["val_f1"])
    logger.info("模型: %s", args.model)
    logger.info("指标: %s", args.metrics)
    if report["val_auc"] < 0.7:
        raise SystemExit("训练失败：val_auc 未达到 0.7")


if __name__ == "__main__":
    main()
