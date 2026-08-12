"""
模型评估: 准确率 / 召回率 / 混淆矩阵.
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.config import settings
from app.engine.feature_registry import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def evaluate(threshold: float = 0.3) -> dict:
    """评估已保存模型."""
    try:
        import xgboost as xgb

        from app.engine.ml_model import get_model_path, load_model

        load_model()
        model_path = get_model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"模型不存在: {model_path}")

        csv_path = PROJECT_ROOT / settings.TRAIN_CSV_PATH
        df = pd.read_csv(csv_path)
        y = df["label"].astype(int).to_numpy()
        X = df[list(FEATURE_COLUMNS)].fillna(0).to_numpy(dtype=float)

        booster = xgb.Booster()
        booster.load_model(str(model_path))
        proba = booster.predict(xgb.DMatrix(X, feature_names=list(FEATURE_COLUMNS)))
        pred = (proba >= threshold).astype(int)

        metrics = {
            "accuracy": round(float(accuracy_score(y, pred)), 4),
            "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
            "auc": round(float(roc_auc_score(y, proba)), 4),
            "threshold": threshold,
            "confusion_matrix": confusion_matrix(y, pred).tolist(),
            "classification_report": classification_report(y, pred, zero_division=0),
        }

        print("=" * 60)
        print("模型评估结果")
        print("=" * 60)
        for key, value in metrics.items():
            if key == "classification_report":
                print(value)
            else:
                print(f"{key}: {value}")

        report_path = PROJECT_ROOT / settings.EVALUATE_REPORT_PATH
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            f"# 模型评估报告\n\n"
            f"- accuracy: {metrics['accuracy']}\n"
            f"- precision: {metrics['precision']}\n"
            f"- recall: {metrics['recall']}\n"
            f"- f1: {metrics['f1']}\n"
            f"- auc: {metrics['auc']}\n"
            f"- threshold: {metrics['threshold']}\n\n"
            f"```\n{metrics['classification_report']}\n```\n",
            encoding="utf-8",
        )
        logger.info("评估报告已写入: %s", report_path)
        return metrics
    except Exception:
        logger.exception("模型评估失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="评估 XGBoost 模型")
    parser.add_argument("--threshold", type=float, default=0.3)
    args = parser.parse_args()
    evaluate(args.threshold)


if __name__ == "__main__":
    main()
