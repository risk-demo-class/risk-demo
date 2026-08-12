"""
XGBoost 模型管理: 加载 / 推理 / 训练 / 兜底.

【重要约定】
  - 特征顺序固定 (FEATURE_COLUMNS), 跟 feature.py 算出的 28 个 key 一一对应
  - 标签二分类: 0=通过/标记, 1=人工审核/拒绝
  - 概率输出: predict_proba[:, 1] 即 P(拒绝)
"""
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

logger = logging.getLogger(__name__)


# 固定 28 维特征顺序 (训练和推理都用这个顺序, 防 dict 顺序不一致导致特征错位)
FEATURE_COLUMNS: list[str] = [
    # 用户维度 (16)
    "user_total_bookings",
    "user_bookings_7d",
    "user_bookings_30d",
    "user_total_amount",
    "user_avg_order_amount",
    "user_max_order_amount",
    "user_refund_change_count",
    "user_refund_rate",
    "user_refund_amount",
    "user_claim_count",
    "user_claim_rate",
    "user_complaint_count",
    "user_traveler_count",
    "user_device_count",
    "user_review_count",
    "user_cancel_count",
    # 订单维度 (9)
    "order_total_amount",
    "order_item_count",
    "order_traveler_count",
    "order_discount_rate",
    "order_pay_interval_sec",
    "order_is_night",
    "order_lead_days",
    "order_trip_days",
    "order_is_overseas",
    # 出行人维度 (3)
    "traveler_total_count",
    "traveler_phone_count",
    "traveler_new_count",
]

assert len(FEATURE_COLUMNS) == 28, f"特征数量必须是 28, 当前 {len(FEATURE_COLUMNS)}"


@dataclass
class MlResult:
    """XGBoost 单次推理结果"""
    score: float           # P(拒绝) ∈ [0, 1]
    decision: str          # 4 档: 通过/标记/人工审核/拒绝
    is_loaded: bool        # 模型是否加载成功 (False 表示走兜底)


_MODEL: Optional[xgb.Booster] = None
_LOADED: bool = False


def get_model() -> Optional[xgb.Booster]:
    """获取加载好的 XGBoost 模型 (None = 没启用/加载失败)"""
    return _MODEL


def is_model_loaded() -> bool:
    """模型是否加载成功."""
    return _LOADED


def load_model(model_path: Optional[str] = None) -> bool:
    """启动时加载 XGBoost 模型. 兜底: 文件不存在/加载失败 → 业务仍可运行."""
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
    """28 维 dict → numpy 数组 (1×28). 缺失用 0.0 兜底."""
    row = []
    for col in FEATURE_COLUMNS:
        v = features.get(col, 0.0)
        try:
            row.append(float(v))
        except (TypeError, ValueError):
            row.append(0.0)
    return np.array([row], dtype=np.float32)


def predict(features: dict) -> MlResult:
    """推理入口: 28 维特征 → P(拒绝) + ML 维度决策. 模型没加载 → 兜底 score=0 通过."""
    if not _LOADED or _MODEL is None:
        return MlResult(score=0.0, decision="通过", is_loaded=False)
    try:
        x = _features_to_array(features)
        dmat = xgb.DMatrix(x, feature_names=FEATURE_COLUMNS)
        prob = float(_MODEL.predict(dmat)[0])
    except Exception as e:
        logger.exception("XGBoost 推理失败, 走兜底: %s", e)
        return MlResult(score=0.0, decision="通过", is_loaded=True)
    return MlResult(score=round(prob, 4), decision=_prob_to_decision(prob), is_loaded=True)


def _prob_to_decision(prob: float) -> str:
    """XGBoost 概率 P(拒绝) ∈ [0,1] → 4 档决策."""
    if prob < settings.ML_PASS_THRESHOLD:
        return "通过"
    elif prob < settings.ML_MARK_THRESHOLD:
        return "标记"
    elif prob < settings.ML_REVIEW_THRESHOLD:
        return "人工审核"
    else:
        return "拒绝"


def train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    model_path: Optional[str] = None,
    num_boost_round: int = 200,
    return_model: bool = False,
    early_stopping_rounds: Optional[int] = None,
) -> dict | tuple[dict, xgb.Booster]:
    """训练 XGBoost 二分类器 + 评估 + 保存."""
    n = len(y)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    pos_ratio = n_pos / n if n else 0.0

    if n < settings.XGB_MIN_SAMPLES:
        logger.warning(
            "样本量 %d < 推荐最小 %d (28 维 × 45 倍经验值), 模型可能欠拟合/过拟合",
            n, settings.XGB_MIN_SAMPLES,
        )

    raw_scale = n_neg / n_pos if n_pos > 0 else 1.0
    scale_pos_weight = min(raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT)
    if raw_scale > settings.XGB_MAX_SCALE_POS_WEIGHT:
        logger.warning(
            "scale_pos_weight %.2f 超过上限 %.2f, 已截断到 %.2f (防止过拟合)",
            raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT, scale_pos_weight,
        )

    if pos_ratio < settings.XGB_MIN_POS_RATIO:
        logger.warning(
            "正例比例 %.1f%% < 推荐最小 %.0f%%, 模型可能假收敛.\n"
            "  建议: python scripts/gen_risk_data.py --balance-pos 重造数据",
            100 * pos_ratio, 100 * settings.XGB_MIN_POS_RATIO,
        )
    if pos_ratio > settings.XGB_MAX_POS_RATIO:
        logger.warning(
            "正例比例 %.1f%% > 推荐最大 %.0f%%, 可能标签有噪声",
            100 * pos_ratio, 100 * settings.XGB_MAX_POS_RATIO,
        )

    esr = early_stopping_rounds if early_stopping_rounds is not None else settings.XGB_EARLY_STOPPING_ROUNDS
    y_tr = y
    y_val = None
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

    booster = None
    if esr and len(eval_set) > 1 and settings.XGB_WARMUP_ROUNDS > 0:
        warmup_params = {**params, "eval_metric": ["logloss"]}
        xgb.train(
            warmup_params,
            dtrain,
            num_boost_round=settings.XGB_WARMUP_ROUNDS,
            evals=eval_set,
            verbose_eval=False,
        )
        booster = xgb.train(
            params,
            dtrain,
            num_boost_round=num_boost_round,
            evals=eval_set,
            early_stopping_rounds=esr,
            verbose_eval=False,
        )
    else:
        booster = xgb.train(
            params,
            dtrain,
            num_boost_round=num_boost_round,
            evals=eval_set,
            verbose_eval=False,
        )

    # 评估: 有验证集用验证集 (更真实), 否则用训练集
    eval_target = dval if y_val is not None else dtrain
    eval_y = y_val if y_val is not None else y_tr
    pred_prob = booster.predict(eval_target)
    pred = (pred_prob >= 0.5).astype(int)
    auc = float(roc_auc_score(eval_y, pred_prob)) if len(set(eval_y)) > 1 else 0.0
    f1 = float(f1_score(eval_y, pred, zero_division=0))
    best_iter = getattr(booster, "best_iteration", None)
    if best_iter is None:
        best_iter = num_boost_round
    best_iter = int(best_iter)

    metrics = {
        "n_samples": n,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "pos_ratio": round(pos_ratio, 4),
        "train_auc": round(auc, 4),
        "train_f1": round(f1, 4),
        "best_iter": best_iter,
        "scale_pos_weight": round(scale_pos_weight, 4),
    }

    if model_path:
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        booster.save_model(model_path)
        logger.info("模型已保存: %s", model_path)

    if return_model:
        return metrics, booster
    return metrics
