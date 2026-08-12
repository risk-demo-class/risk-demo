"""
XGBoost 模型管理: 加载 / 推理 / 训练 / 兜底.

设计:
- 懒加载: import 时不阻塞, 只有 predict 前确保加载.
- 缺失模型 / 加载失败时降级为纯规则, 业务不停.
- 特征顺序来自 config/features.yaml, 训练与推理保持一致.
"""

import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import settings
from app.engine.feature_registry import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

_MODEL = None
_LOADED = False
_LOAD_LOCK = threading.Lock()


@dataclass
class MlResult:
    """模型预测结果."""

    probability: float
    score: float
    decision: str
    is_loaded: bool


def get_model_path() -> Path:
    """模型路径相对项目根目录."""
    if Path(settings.XGB_MODEL_PATH).is_absolute():
        return Path(settings.XGB_MODEL_PATH)
    return Path(__file__).resolve().parents[2] / settings.XGB_MODEL_PATH


def load_model(model_path: Optional[str] = None) -> bool:
    """加载 XGBoost 模型, 失败时降级纯规则."""
    global _MODEL, _LOADED
    with _LOAD_LOCK:
        if not settings.XGB_ENABLED:
            logger.warning("XGB_ENABLED=False, 使用纯规则")
            _LOADED = False
            return False
        try:
            import xgboost as xgb

            path = Path(model_path) if model_path else get_model_path()
            if not path.exists():
                logger.warning("模型文件不存在, 使用纯规则: %s", path)
                _LOADED = False
                return False
            _MODEL = xgb.Booster()
            _MODEL.load_model(str(path))
            _LOADED = True
            logger.info("XGBoost 模型加载成功: %s", path)
            return True
        except Exception:
            logger.exception("XGBoost 模型加载失败, 使用纯规则")
            _LOADED = False
            return False


def _features_to_array(features: dict) -> np.ndarray:
    """特征 dict -> 固定顺序 ndarray."""
    try:
        row = [float(features.get(name, 0.0) or 0.0) for name in FEATURE_COLUMNS]
        return np.array([row], dtype=np.float32)
    except Exception:
        logger.exception("特征转数组失败")
        raise


def _prob_to_risk_score(prob: float, k: float = 3.0) -> float:
    """拒绝概率 -> 0-100 风险分."""
    if prob <= 0:
        return 0.0
    if prob >= 1:
        return 100.0
    return round(100 * (1 - math.exp(-k * prob)), 2)


def _prob_to_decision(prob: float) -> str:
    """概率 -> 4 档决策."""
    if prob >= settings.ML_REVIEW_THRESHOLD:
        return "拒绝"
    if prob >= settings.ML_MARK_THRESHOLD:
        return "人工审核"
    if prob >= settings.ML_PASS_THRESHOLD:
        return "标记"
    return "通过"


def predict(features: dict) -> MlResult:
    """在线推理, 模型未加载时返回 0 分."""
    try:
        if not _LOADED or _MODEL is None:
            return MlResult(probability=0.0, score=0.0, decision="通过", is_loaded=False)

        import xgboost as xgb

        array = _features_to_array(features)
        dmatrix = xgb.DMatrix(array, feature_names=list(FEATURE_COLUMNS))
        prob = float(_MODEL.predict(dmatrix)[0])
        score = _prob_to_risk_score(prob)
        decision = _prob_to_decision(prob)
        return MlResult(probability=prob, score=score, decision=decision, is_loaded=True)
    except Exception:
        logger.exception("XGBoost 预测失败, 使用 0 分兜底")
        return MlResult(probability=0.0, score=0.0, decision="通过", is_loaded=False)


def train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[list[str]] = None,
) -> tuple[dict, object]:
    """
    训练 XGBoost 并保存模型.

    返回 (metrics, model).
    metrics 至少包含:
    - accuracy / precision / recall / f1 / auc
    - confusion_matrix
    - best_f1_threshold
    - best_iteration
    - is_fake_convergence
    """
    try:
        from sklearn.metrics import (
            accuracy_score,
            confusion_matrix,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )
        from sklearn.model_selection import train_test_split
        import xgboost as xgb

        names = feature_names or list(FEATURE_COLUMNS)
        X_train, X_val, y_train, y_val = train_test_split(
            X,
            y,
            test_size=settings.XGB_TEST_SIZE,
            stratify=y,
            random_state=42,
        )

        neg_count = int((y_train == 0).sum())
        pos_count = int((y_train == 1).sum())
        raw_weight = neg_count / max(pos_count, 1)
        scale_pos_weight = min(raw_weight, settings.XGB_MAX_SCALE_POS_WEIGHT)

        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=names)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=names)

        params = {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "max_depth": settings.XGB_MAX_DEPTH,
            "eta": settings.XGB_LEARNING_RATE,
            "min_child_weight": settings.XGB_MIN_CHILD_WEIGHT,
            "alpha": settings.XGB_REG_ALPHA,
            "lambda": settings.XGB_REG_LAMBDA,
            "gamma": settings.XGB_GAMMA,
            "subsample": settings.XGB_SUBSAMPLE,
            "colsample_bytree": settings.XGB_COLSAMPLE_BYTREE,
            "scale_pos_weight": scale_pos_weight,
            "seed": 42,
        }

        evals_result = {}
        warmup_rounds = settings.XGB_WARMUP_ROUNDS
        model = xgb.train(
            params,
            dtrain,
            num_boost_round=warmup_rounds,
            evals=[(dtrain, "train"), (dval, "val")],
            evals_result=evals_result,
            verbose_eval=False,
        )
        model = xgb.train(
            params,
            dtrain,
            num_boost_round=200,
            xgb_model=model,
            evals=[(dtrain, "train"), (dval, "val")],
            evals_result=evals_result,
            early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
            maximize=True,
            verbose_eval=False,
        )

        val_proba = model.predict(dval)
        auc = float(roc_auc_score(y_val, val_proba))

        best_threshold = 0.5
        best_f1 = 0.0
        for threshold in [round(t, 2) for t in np.arange(0.10, 0.86, 0.05)]:
            pred = (val_proba >= threshold).astype(int)
            f1 = f1_score(y_val, pred, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = threshold

        pred = (val_proba >= best_threshold).astype(int)
        accuracy = float(accuracy_score(y_val, pred))
        precision = float(precision_score(y_val, pred, zero_division=0))
        recall = float(recall_score(y_val, pred, zero_division=0))
        f1 = float(f1_score(y_val, pred, zero_division=0))
        cm = confusion_matrix(y_val, pred).tolist()
        baseline_acc = float(max(1 - y_val.mean(), y_val.mean()))

        val_auc_curve = evals_result.get("val", {}).get("auc", [])
        if val_auc_curve:
            best_iteration = max(int(np.argmax(val_auc_curve)) + 1, warmup_rounds)
        else:
            best_iteration = int(getattr(model, "best_iteration", 0) or 0)
        is_fake_convergence = (
            best_iteration < settings.XGB_MIN_BEST_ITER
            or auc < settings.XGB_MIN_VAL_AUC
            or f1 < settings.XGB_MIN_VAL_F1
            or accuracy < baseline_acc + 0.02
        )

        path = get_model_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(path))

        metrics = {
            "n_train": int(len(y_train)),
            "n_val": int(len(y_val)),
            "pos_ratio_train": round(pos_count / max(len(y_train), 1), 4),
            "scale_pos_weight": round(scale_pos_weight, 4),
            "best_iteration": best_iteration,
            "auc": round(auc, 4),
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "confusion_matrix": cm,
            "best_f1_threshold": best_threshold,
            "baseline_acc": round(baseline_acc, 4),
            "is_fake_convergence": is_fake_convergence,
            "model_path": str(path),
        }
        logger.info("XGBoost 训练完成: %s", metrics)
        return metrics, model
    except Exception:
        logger.exception("XGBoost 训练失败")
        raise


def _schedule_load() -> None:
    """模块导入时懒加载, 不阻塞业务."""
    if settings.XGB_ENABLED:
        load_model()


_schedule_load()
