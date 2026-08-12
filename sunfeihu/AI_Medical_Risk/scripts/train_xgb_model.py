"""训练医疗风控 XGBoost 模型，并用独立校准集做 Platt 概率校准。"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.engine.feature import FEATURE_COLUMNS  # noqa: E402
from app.engine.training_data import collect_training_dataset  # noqa: E402


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -40, 40)
    return 1.0 / (1.0 + np.exp(-values))


def _best_f1_threshold(labels: np.ndarray, probabilities: np.ndarray) -> tuple[float, float]:
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in np.linspace(0.05, 0.95, 181):
        score = f1_score(labels, probabilities >= threshold, zero_division=0)
        if score > best_f1:
            best_threshold, best_f1 = float(threshold), float(score)
    return round(best_threshold, 4), round(best_f1, 4)


async def train(limit: int) -> dict:
    async with AsyncSessionLocal() as db:
        dataset = await collect_training_dataset(db, limit=limit)
    X, y = dataset.features, dataset.labels
    if len(X) < 50 or len(np.unique(y)) != 2:
        raise RuntimeError("训练样本不足或弱监督标签只有一个类别，请先初始化完整合成业务数据")

    # 60% 训练、20% 概率校准、20% 最终验证；三部分均保持正负例比例。
    X_train, X_hold, y_train, y_hold = train_test_split(
        X, y, test_size=settings.XGB_TEST_SIZE + settings.XGB_CALIBRATION_SIZE,
        stratify=y, random_state=settings.XGB_RANDOM_STATE,
    )
    validation_fraction = settings.XGB_TEST_SIZE / (settings.XGB_TEST_SIZE + settings.XGB_CALIBRATION_SIZE)
    X_cal, X_val, y_cal, y_val = train_test_split(
        X_hold, y_hold, test_size=validation_fraction,
        stratify=y_hold, random_state=settings.XGB_RANDOM_STATE,
    )
    positives = int(y_train.sum())
    negatives = int(len(y_train) - positives)
    scale_pos_weight = negatives / positives if positives else 1.0
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["auc", "logloss"],
        "max_depth": 5,
        "eta": 0.05,
        "min_child_weight": 3,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.1,
        "reg_lambda": 1.2,
        "scale_pos_weight": scale_pos_weight,
        "seed": settings.XGB_RANDOM_STATE,
        "verbosity": 0,
    }
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_COLUMNS)
    dcal = xgb.DMatrix(X_cal, label=y_cal, feature_names=FEATURE_COLUMNS)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
    booster = xgb.train(
        params, dtrain, num_boost_round=settings.XGB_NUM_BOOST_ROUND,
        evals=[(dtrain, "train"), (dcal, "calibration")],
        early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        verbose_eval=False,
    )
    best_iteration = int(booster.best_iteration)
    prediction_args = {"iteration_range": (0, best_iteration + 1)}

    # Platt scaling：以校准集的原始 margin 拟合 logistic，验证集只用于最终指标。
    cal_margin = booster.predict(dcal, output_margin=True, **prediction_args)
    calibrator = LogisticRegression(random_state=settings.XGB_RANDOM_STATE)
    calibrator.fit(cal_margin.reshape(-1, 1), y_cal)
    coefficient = float(calibrator.coef_[0, 0])
    intercept = float(calibrator.intercept_[0])
    val_margin = booster.predict(dval, output_margin=True, **prediction_args)
    val_probability = _sigmoid(coefficient * val_margin + intercept)
    best_threshold, validation_f1 = _best_f1_threshold(y_val, val_probability)
    validation_auc = float(roc_auc_score(y_val, val_probability))

    model_path = PROJECT_ROOT / settings.XGB_MODEL_PATH
    metadata_path = PROJECT_ROOT / settings.XGB_METADATA_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(model_path)
    importance = booster.get_score(importance_type="gain")
    top_features = sorted(importance.items(), key=lambda item: item[1], reverse=True)[:10]
    decision_thresholds = {
        "pass": round(max(0.02, best_threshold * 0.35), 4),
        "mark": round(max(0.05, best_threshold * 0.65), 4),
        "review": best_threshold,
    }
    metrics = {
        "sample_count": int(len(y)),
        "positive_count": int(y.sum()),
        "negative_count": int(len(y) - y.sum()),
        "positive_ratio": round(float(y.mean()), 4),
        "train_count": int(len(y_train)),
        "calibration_count": int(len(y_cal)),
        "validation_count": int(len(y_val)),
        "validation_auc": round(validation_auc, 4),
        "validation_f1": validation_f1,
        "best_threshold": best_threshold,
        "quality_passed": validation_auc >= settings.XGB_MIN_VAL_AUC and validation_f1 >= settings.XGB_MIN_VAL_F1,
    }
    metadata = {
        "model_version": "medical-xgb-p2-v1",
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "feature_columns": FEATURE_COLUMNS,
        "label_strategy": "教学型规则弱监督：人工审核或拒绝规则命中记为正例；规则结果不作为模型特征",
        "split_strategy": "stratified 60% train / 20% calibration / 20% validation",
        "probability_calibration": "Platt scaling on independent calibration split",
        "platt_calibration": {"coefficient": coefficient, "intercept": intercept},
        "decision_thresholds": decision_thresholds,
        "best_iteration": best_iteration,
        "metrics": metrics,
        "feature_importance_top10": [{"feature": name, "gain": round(float(gain), 4)} for name, gain in top_features],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**metrics, "model_path": str(model_path), "metadata_path": str(metadata_path), "feature_importance_top10": metadata["feature_importance_top10"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="训练医疗风控 XGBoost 模型")
    parser.add_argument("--limit", type=int, default=settings.XGB_TRAIN_DATA_LIMIT)
    args = parser.parse_args()
    result = asyncio.run(train(args.limit))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["quality_passed"]:
        print("警告：验证指标未达到教学验收线 AUC>=0.70 且 F1>=0.50。")


if __name__ == "__main__":
    main()
