"""
XGBoost 模型管理 (银行语义, 11 维特征): 加载 / 推理 / 训练 / 兜底.

【约定】
  - 特征顺序固定 (FEATURE_COLUMNS), 跟 Bank-Risk engine.feature.FEATURE_ORDER 一一对应 (11 维)
  - 标签二分类: 0=pass/review, 1=reject/freeze/report
  - 概率输出: predict_proba[:, 1] 即 P(拒绝)
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import xgboost as xgb
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

from app.config import settings
from app.engine import feature as bank_feature

logger = logging.getLogger(__name__)


# 固定 11 维特征顺序 (与 Bank-Risk engine.feature.FEATURE_ORDER 对齐)
FEATURE_COLUMNS: list[str] = list(bank_feature.FEATURE_ORDER)
assert len(FEATURE_COLUMNS) == 11, f"特征数量必须是 11, 当前 {len(FEATURE_COLUMNS)}"


@dataclass
class MlResult:
    score: float
    decision: str
    is_loaded: bool


_MODEL: Optional[xgb.Booster] = None
_LOADED: bool = False


def get_model() -> Optional[xgb.Booster]:
    return _MODEL


def is_model_loaded() -> bool:
    return _LOADED


def load_model(model_path: Optional[str] = None) -> bool:
    global _MODEL, _LOADED
    if not settings.XGB_ENABLED:
        logger.info("XGBoost 已关闭 (XGB_ENABLED=False), 决策走纯规则模式")
        return False

    if model_path:
        path = model_path
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        path = str(project_root / settings.XGB_MODEL_PATH)
    if not os.path.exists(path):
        logger.warning("XGBoost 模型文件不存在: %s, 决策走纯规则模式", path)
        return False

    try:
        _MODEL = xgb.Booster()
        _MODEL.load_model(path)
        _LOADED = True
        logger.info("XGBoost 模型加载成功: %s, features=%d", path, _MODEL.num_features())
        return True
    except Exception as e:
        logger.exception("XGBoost 模型加载失败: %s, 错误: %s", path, e)
        _MODEL = None
        _LOADED = False
        return False


def _features_to_array(features: dict) -> np.ndarray:
    row = []
    for col in FEATURE_COLUMNS:
        v = features.get(col, 0.0)
        try:
            row.append(float(v))
        except (TypeError, ValueError):
            row.append(0.0)
    return np.array([row], dtype=np.float32)


def predict(features: dict) -> MlResult:
    if not _LOADED or _MODEL is None:
        return MlResult(score=0.0, decision="pass", is_loaded=False)
    try:
        x = _features_to_array(features)
        dmat = xgb.DMatrix(x, feature_names=FEATURE_COLUMNS)
        prob = float(_MODEL.predict(dmat)[0])
    except Exception as e:
        logger.exception("XGBoost 推理失败, 走兜底: %s", e)
        return MlResult(score=0.0, decision="pass", is_loaded=True)
    return MlResult(score=round(prob, 4), decision=_prob_to_decision(prob), is_loaded=True)


def _prob_to_decision(prob: float) -> str:
    if prob < settings.ML_PASS_THRESHOLD:
        return "pass"
    elif prob < settings.ML_MARK_THRESHOLD:
        return "review"
    elif prob < settings.ML_REVIEW_THRESHOLD:
        return "reject"
    else:
        return "freeze"


def train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    model_path: Optional[str] = None,
    num_boost_round: int = 200,
    return_model: bool = False,
    early_stopping_rounds: Optional[int] = None,
) -> dict | tuple[dict, xgb.Booster]:
    """训练 XGBoost 二分类器 + 评估 + 保存 (11 维银行特征)."""
    n = len(y)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    pos_ratio = n_pos / n if n else 0.0

    if n < settings.XGB_MIN_SAMPLES:
        logger.warning("样本量 %d < 推荐最小 %d, 模型可能欠拟合/过拟合", n, settings.XGB_MIN_SAMPLES)

    raw_scale = n_neg / n_pos if n_pos > 0 else 1.0
    scale_pos_weight = min(raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT)
    if raw_scale > settings.XGB_MAX_SCALE_POS_WEIGHT:
        logger.warning("scale_pos_weight %.2f 超过上限, 已截断到 %.2f", raw_scale, scale_pos_weight)

    if pos_ratio < settings.XGB_MIN_POS_RATIO:
        logger.warning("正例比例 %.1f%% < 推荐最小 %.0f%%", 100 * pos_ratio, 100 * settings.XGB_MIN_POS_RATIO)
    if pos_ratio > settings.XGB_MAX_POS_RATIO:
        logger.warning("正例比例 %.1f%% > 推荐最大 %.0f%%", 100 * pos_ratio, 100 * settings.XGB_MAX_POS_RATIO)

    esr = early_stopping_rounds if early_stopping_rounds is not None else settings.XGB_EARLY_STOPPING_ROUNDS
    if esr and n >= 10:
        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42,
        )
        dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_COLUMNS)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
        eval_set = [(dtrain, "train"), (dval, "val")]
    else:
        dtrain = xgb.DMatrix(X, label=y, feature_names=FEATURE_COLUMNS)
        eval_set = [(dtrain, "train")]

    params = {
        "objective": "binary:logistic",
        "max_depth": settings.XGB_MAX_DEPTH,
        "eta": settings.XGB_LEARNING_RATE,
        "min_child_weight": settings.XGB_MIN_CHILD_WEIGHT,
        "reg_alpha": settings.XGB_REG_ALPHA,
        "reg_lambda": settings.XGB_REG_LAMBDA,
        "gamma": settings.XGB_GAMMA,
        "subsample": settings.XGB_SUBSAMPLE,
        "colsample_bytree": settings.XGB_COLSAMPLE_BYTREE,
        "eval_metric": [settings.XGB_EARLY_STOP_METRIC, "logloss"],
        "verbosity": 0,
        "scale_pos_weight": scale_pos_weight,
    }

    if esr and len(eval_set) > 1 and settings.XGB_WARMUP_ROUNDS > 0:
        warmup_params = {**params, "eval_metric": ["logloss"]}
        warmup_booster = xgb.train(warmup_params, dtrain, num_boost_round=settings.XGB_WARMUP_ROUNDS,
                                   evals=eval_set, verbose_eval=False)
        booster = xgb.train(params, dtrain, num_boost_round=num_boost_round, evals=eval_set,
                            early_stopping_rounds=esr, xgb_model=warmup_booster, verbose_eval=False)
    else:
        booster = xgb.train(params, dtrain, num_boost_round=num_boost_round, evals=eval_set,
                            early_stopping_rounds=esr if len(eval_set) > 1 else None, verbose_eval=False)

    y_pred_prob = booster.predict(xgb.DMatrix(X, feature_names=FEATURE_COLUMNS))
    y_pred = (y_pred_prob >= 0.5).astype(int)
    tp = int(np.sum((y_pred == 1) & (y == 1)))
    fp = int(np.sum((y_pred == 1) & (y == 0)))
    fn = int(np.sum((y_pred == 0) & (y == 1)))
    tn = int(np.sum((y_pred == 0) & (y == 0)))
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = f1_score(y, y_pred, zero_division=0)
    auc = roc_auc_score(y, y_pred_prob) if n_pos > 0 and n_neg > 0 else 0.0

    val_metrics = {}
    if len(eval_set) > 1:
        y_val_pred_prob = booster.predict(dval)
        best_f1, best_thr = 0.0, 0.5
        for thr in [round(x * 0.01, 2) for x in range(10, 90, 5)]:
            y_val_pred_t = (y_val_pred_prob >= thr).astype(int)
            f1_t = f1_score(y_val, y_val_pred_t, zero_division=0)
            if f1_t > best_f1:
                best_f1 = f1_t
                best_thr = thr
        y_val_pred = (y_val_pred_prob >= best_thr).astype(int)
        val_acc = float(np.mean(y_val_pred == y_val))
        val_f1 = float(best_f1)
        val_auc = roc_auc_score(y_val, y_val_pred_prob) if len(np.unique(y_val)) > 1 else 0.0
        val_metrics = {
            "n_val": int(len(y_val)), "val_accuracy": round(val_acc, 4),
            "val_f1": round(val_f1, 4), "val_auc": round(float(val_auc), 4),
            "best_f1_threshold": round(best_thr, 2),
        }

    if model_path:
        save_path = model_path
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        save_path = str(project_root / settings.XGB_MODEL_PATH)
    booster.save_model(save_path)

    best_iter = booster.best_iteration if hasattr(booster, "best_iteration") and booster.best_iteration is not None else num_boost_round
    metrics = {
        "n_train": n, "n_pos": n_pos, "n_neg": n_neg, "pos_ratio": round(pos_ratio, 4),
        "scale_pos_weight": round(scale_pos_weight, 4), "raw_scale_pos_weight": round(raw_scale, 4),
        "best_iteration": int(best_iter), "accuracy": round(accuracy, 4),
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(float(f1), 4),
        "auc": round(float(auc), 4), "model_path": save_path,
        "baseline_accuracy": round(n_neg / n if n else 0.0, 4),
    }
    metrics.update(val_metrics)
    if return_model:
        return metrics, booster
    return metrics


def _schedule_load():
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(load_model))
    except RuntimeError:
        load_model()


_schedule_load()
