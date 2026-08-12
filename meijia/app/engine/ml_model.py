"""教育行业固定 25 维特征顺序；模型训练与推理必须共同引用此列表。

模块保持同步、纯计算 (不依赖 HTTP / DB), 便于单测。
固定 25 维特征顺序 (FEATURE_COLUMNS), 标签二分类:
    0 = 通过/标记, 1 = 人工审核/拒绝
概率输出: predict_proba[:,1] 即 P(拒绝)。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import xgboost as xgb

from app.config import settings

logger = logging.getLogger(__name__)

FEATURE_COLUMNS: list[str] = [
    # 账号/身份族（8）
    "account_age_days", "is_student", "is_real_name_verified", "new_account_flag",
    "device_count_180d", "device_student_count", "student_blacklist_hit", "user_order_count_30d",
    # 报名/交易族（8）
    "buyer_paid_amount_1h", "buyer_order_count_1h", "course_new_student_count_7d",
    "course_linked_new_student_count_7d", "order_total_amount", "expected_finish_days",
    "payment_account_user_count_7d", "order_course_price_ratio",
    # 学习/退费/认证/直播族（9）
    "study_minutes_before_refund", "completion_rate", "days_since_last_active",
    "user_refund_count_90d", "user_refund_amount_90d", "refund_rate_90d",
    "session_reward_net_amount", "credential_mismatch", "credential_no_record",
]

assert len(FEATURE_COLUMNS) == 25
assert len(set(FEATURE_COLUMNS)) == 25


@dataclass(frozen=True)
class MlResult:
    """XGBoost 单次推理结果。"""

    score: float      # P(拒绝) ∈ [0, 1]
    decision: str     # 4 档: 通过/标记/人工审核/拒绝
    is_loaded: bool   # 模型是否真正加载成功 (False 表示走兜底)


# 模型全局单例 (启动时初始化一次; 训练脚本会热加载到内存以便立刻生效)
_MODEL: Optional[xgb.Booster] = None
_LOADED: bool = False


def get_model() -> Optional[xgb.Booster]:
    return _MODEL


def is_model_loaded() -> bool:
    return _LOADED


def resolve_model_path(model_path: Optional[str] = None) -> str:
    """把配置里的相对路径解析成项目根下的绝对路径。"""
    if model_path:
        return os.path.abspath(model_path)
    return str(Path(__file__).resolve().parents[2] / settings.XGB_MODEL_PATH)


def load_model(model_path: Optional[str] = None) -> bool:
    """启动时加载 XGBoost 模型。文件不存在/加载失败 → 业务仍走纯规则兜底。"""
    global _MODEL, _LOADED
    _MODEL, _LOADED = None, False
    if not settings.XGB_ENABLED:
        logger.info("XGBoost 已关闭 (RISK_XGB_ENABLED=False), 决策走纯规则")
        return False
    path = resolve_model_path(model_path)
    if not os.path.exists(path):
        logger.warning("XGBoost 模型文件不存在: %s, 决策走纯规则", path)
        return False
    try:
        booster = xgb.Booster()
        booster.load_model(path)
        _MODEL, _LOADED = booster, True
        logger.info("XGBoost 模型加载成功: %s, features=%d", path, booster.num_features())
        return True
    except Exception:
        logger.exception("XGBoost 模型加载失败: %s", path)
        _MODEL, _LOADED = None, False
        return False


def _features_to_array(features: dict) -> np.ndarray:
    """25 维 dict → numpy 数组 (1×25)。缺失/非数值统一 0.0 兜底。"""
    row = []
    for col in FEATURE_COLUMNS:
        v = features.get(col, 0.0)
        try:
            row.append(float(v))
        except (TypeError, ValueError):
            row.append(0.0)
    return np.array([row], dtype=np.float32)


def _prob_to_decision(prob: float) -> str:
    """P(拒绝) ∈ [0,1] → 4 档决策 (用 RISK_ML_*_THRESHOLD)。"""
    if prob < settings.ML_PASS_THRESHOLD:
        return "通过"
    if prob < settings.ML_MARK_THRESHOLD:
        return "标记"
    if prob < settings.ML_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def predict(features: dict) -> MlResult:
    """推理入口: 25 维特征 → MlResult。模型未加载 → 兜底 (0, 通过)。"""
    if not _LOADED or _MODEL is None:
        return MlResult(score=0.0, decision="通过", is_loaded=False)
    try:
        x = _features_to_array(features)
        dmat = xgb.DMatrix(x, feature_names=FEATURE_COLUMNS)
        prob = float(_MODEL.predict(dmat)[0])
    except Exception:
        logger.exception("XGBoost 推理失败, 走兜底")
        return MlResult(score=0.0, decision="通过", is_loaded=True)
    return MlResult(score=round(prob, 4), decision=_prob_to_decision(prob), is_loaded=True)


def train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    model_path: Optional[str] = None,
    num_boost_round: int = 200,
    return_model: bool = False,
    early_stopping_rounds: Optional[int] = None,
) -> dict | tuple[dict, xgb.Booster]:
    """训练 XGBoost 二分类器 (0=通过/标记, 1=人工审核/拒绝) + 评估 + 保存。

    return_model=True 时返回 (metrics_dict, booster); 否则只返回 metrics_dict。
    模型默认保存到配置的 RISK_XGB_MODEL_PATH。
    """
    from sklearn.metrics import f1_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    n = len(y)
    n_pos = int(np.sum(y == 1))
    n_neg = n - n_pos
    pos_ratio = n_pos / n if n else 0.0

    if n < settings.XGB_MIN_SAMPLES:
        logger.warning(
            "样本量 %d < 推荐最小 %d, 模型可能欠拟合/过拟合, 建议积累更多评估数据后重训",
            n, settings.XGB_MIN_SAMPLES,
        )
    raw_scale = n_neg / n_pos if n_pos > 0 else 1.0
    scale_pos_weight = min(raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT)

    esr = early_stopping_rounds if early_stopping_rounds is not None else settings.XGB_EARLY_STOPPING_ROUNDS
    if esr and n >= 10:
        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42,
        )
        dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_COLUMNS)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
        eval_set = [(dtrain, "train"), (dval, "val")]
    else:
        X_tr, y_tr = X, y
        dtrain = xgb.DMatrix(X, label=y, feature_names=FEATURE_COLUMNS)
        eval_set = [(dtrain, "train")]
        X_val = y_val = None

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

    booster = xgb.train(
        params, dtrain, num_boost_round=num_boost_round,
        evals=eval_set, early_stopping_rounds=esr if (esr and len(eval_set) > 1) else None,
        verbose_eval=False,
    )

    y_pred = (booster.predict(dtrain) >= 0.5).astype(int)
    if X_val is not None:
        # 有验证集切分时, 训练集预测对齐 y_tr (dtrain 是切分后的子集)
        accuracy = float(np.mean(y_pred == y_tr))
        f1 = float(f1_score(y_tr, y_pred, zero_division=0))
    else:
        accuracy = float(np.mean(y_pred == y))
        f1 = float(f1_score(y, y_pred, zero_division=0))
    metrics = {
        "n": n, "n_pos": n_pos, "n_neg": n_neg, "pos_ratio": round(pos_ratio, 4),
        "accuracy": round(accuracy, 4), "f1": round(f1, 4),
    }
    if X_val is not None and n_pos > 0 and n_neg > 0:
        val_pred = (booster.predict(dval) >= 0.5).astype(int)
        try:
            metrics["val_auc"] = round(float(roc_auc_score(y_val, booster.predict(dval))), 4)
            metrics["val_f1"] = round(float(f1_score(y_val, val_pred, zero_division=0)), 4)
        except ValueError:
            metrics["val_auc"] = 0.0
            metrics["val_f1"] = 0.0

    path = resolve_model_path(model_path)
    booster.save_model(path)
    logger.info("XGBoost 模型已保存: %s (n=%d, pos=%d)", path, n, n_pos)

    if return_model:
        return metrics, booster
    return metrics

