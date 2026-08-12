"""
银行风控系统 - XGBoost 模型管理
==============================
模型加载 / 推理 / 训练 / 评估.

【模型职责】
  二分类: 预测 P(拒绝) ∈ [0, 1]
  - 标签 0: 低风险 (通过/标记) — 正常放行
  - 标签 1: 高风险 (人工审核/拒绝) — 需要拦截

【特征对齐】
  30 维特征顺序固定 (FEATURE_COLUMNS), 跟 feature.py 的 compute_all_features 返回值一一对应.
  改特征列表前必须同步 feature.py 和本文件的 FEATURE_COLUMNS.

【双轨融合公式 (decision.py 调用)】
  rule_score = max(规则分) + BONUS × (额外命中数)   (规则维度, 0-100)
  ml_score_100 = sigmoid_calibrate(P(拒绝))          (ML 维度, 0-100)
  final_score  = α × rule_score + β × ml_score_100   (α+β=1, 默认各 0.5)

【ML 概率校准公式】
  直接用 P(拒绝) × 100 是量纲错配 (概率空间 ≠ 风险分空间).
  校准: risk_score = 100 × (1 - exp(-k × prob)), k=3
  校准点: prob=0.1 → 26, 0.3 → 59, 0.5 → 78, 0.7 → 90, 0.9 → 97
"""
import asyncio
import logging
import math
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

# 固定 30 维特征顺序
FEATURE_COLUMNS: list[str] = [
    "user_geo_mismatch", "user_login_fail_1h", "user_txn_1h_count",
    "user_txn_0_5_count", "user_txn_24h_amount", "user_small_txn_24h",
    "user_cards_count", "user_recent_changepwd", "user_recent_changephone",
    "user_profile_changes_24h",
    "txn_amount", "txn_hour", "txn_is_night", "txn_channel",
    "txn_to_same_bank", "txn_amount_near_threshold", "txn_is_cross_border",
    "txn_credit_usage_ratio",
    "device_age_days", "device_user_count", "device_is_emulator",
    "device_is_root", "device_status",
    "ip_is_proxy", "ip_is_tor", "ip_user_count",
    "loan_amount", "loan_debt_ratio", "loan_credit_query_1m",
    "loan_income_gap_ratio",
]
assert len(FEATURE_COLUMNS) == 30, f"特征数量必须是 30, 当前 {len(FEATURE_COLUMNS)}"


@dataclass
class MlResult:
    """XGBoost 单次推理结果"""
    score: float           # P(拒绝) ∈ [0, 1]
    decision: str          # 4 档: 通过/标记/人工审核/拒绝
    is_loaded: bool        # 模型是否加载成功


# 全局单例
_MODEL: Optional[xgb.Booster] = None
_LOADED: bool = False


def get_model() -> Optional[xgb.Booster]:
    return _MODEL


def is_model_loaded() -> bool:
    return _LOADED


def load_model(model_path: Optional[str] = None) -> bool:
    """启动时加载 XGBoost 模型."""
    global _MODEL, _LOADED
    if not settings.XGB_ENABLED:
        logger.info("XGBoost 已关闭, 决策走纯规则模式")
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
        logger.exception("XGBoost 模型加载失败: %s", e)
        _MODEL = None
        _LOADED = False
        return False


def _features_to_array(features: dict) -> np.ndarray:
    """30 维 dict → numpy 数组 (1×30). 缺失用 0.0 兜底."""
    row = []
    for col in FEATURE_COLUMNS:
        v = features.get(col, 0.0)
        try:
            row.append(float(v))
        except (TypeError, ValueError):
            row.append(0.0)
    return np.array([row], dtype=np.float32)


def predict(features: dict) -> MlResult:
    """推理入口: 30 维 → P(拒绝) + ML 决策."""
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
    if prob < settings.ML_PASS_THRESHOLD:
        return "通过"
    elif prob < settings.ML_MARK_THRESHOLD:
        return "标记"
    elif prob < settings.ML_REVIEW_THRESHOLD:
        return "人工审核"
    else:
        return "拒绝"


def ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(拒绝) → 0-100 风险分 (sigmoid 校准)."""
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    model_path: Optional[str] = None,
    num_boost_round: int = 200,
    return_model: bool = False,
    early_stopping_rounds: Optional[int] = None,
) -> dict | tuple[dict, xgb.Booster]:
    """
    训练 XGBoost 二分类器 + 评估 + 保存.

    参数:
      X: (N, 30) float32 特征矩阵
      y: (N,) int 标签 (0=低风险, 1=高风险)
      model_path: 模型保存路径
      num_boost_round: 最大训练轮数
      return_model: 是否返回 booster (用于输出特征重要性)
      early_stopping_rounds: 早停轮数, None 用默认值

    返回:
      metrics dict (含 val_auc, val_f1 等), 或 (metrics, booster) 元组
    """
    n = len(y)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    pos_ratio = n_pos / n if n else 0.0

    # 样本量检查
    if n < settings.XGB_MIN_SAMPLES:
        logger.warning("样本量 %d < 推荐最小 %d, 模型可能欠拟合", n, settings.XGB_MIN_SAMPLES)

    # 样本平衡
    raw_scale = n_neg / n_pos if n_pos > 0 else 1.0
    scale_pos_weight = min(raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT)

    # 正例比例警告
    if pos_ratio < settings.XGB_MIN_POS_RATIO:
        logger.warning("正例比例 %.1f%% < 推荐 %.0f%%, 模型可能假收敛", 100 * pos_ratio, 100 * settings.XGB_MIN_POS_RATIO)

    # 80/20 stratify 拆分
    esr = early_stopping_rounds if early_stopping_rounds is not None else settings.XGB_EARLY_STOPPING_ROUNDS
    if esr and n >= 10:
        X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42)
        dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_COLUMNS)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
        eval_set = [(dtrain, "train"), (dval, "val")]
    else:
        dtrain = xgb.DMatrix(X, label=y, feature_names=FEATURE_COLUMNS)
        eval_set = [(dtrain, "train")]

    # 训练参数
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

    # Warmup 防假收敛
    if esr and len(eval_set) > 1 and settings.XGB_WARMUP_ROUNDS > 0:
        warmup_params = {**params, "eval_metric": ["logloss"]}
        warmup_booster = xgb.train(warmup_params, dtrain, num_boost_round=settings.XGB_WARMUP_ROUNDS,
                                   evals=eval_set, verbose_eval=False)
        booster = xgb.train(params, dtrain, num_boost_round=num_boost_round,
                            evals=eval_set, early_stopping_rounds=esr,
                            xgb_model=warmup_booster, verbose_eval=False)
    else:
        booster = xgb.train(params, dtrain, num_boost_round=num_boost_round,
                            evals=eval_set,
                            early_stopping_rounds=esr if len(eval_set) > 1 else None,
                            verbose_eval=False)

    # 评估: 全量
    y_pred_prob = booster.predict(xgb.DMatrix(X, feature_names=FEATURE_COLUMNS))
    y_pred = (y_pred_prob >= 0.5).astype(int)
    accuracy = float(np.mean(y_pred == y))
    f1 = f1_score(y, y_pred, zero_division=0)
    auc = roc_auc_score(y, y_pred_prob) if n_pos > 0 and n_neg > 0 else 0.0

    # 评估: 验证集
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
            "n_val": int(len(y_val)),
            "val_accuracy": round(val_acc, 4),
            "val_f1": round(val_f1, 4),
            "val_auc": round(float(val_auc), 4),
            "best_f1_threshold": round(best_thr, 2),
        }

    # 保存模型
    if model_path:
        save_path = model_path
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        save_path = str(project_root / settings.XGB_MODEL_PATH)
    booster.save_model(save_path)

    best_iter = booster.best_iteration if hasattr(booster, "best_iteration") and booster.best_iteration is not None else num_boost_round

    logger.info(
        "XGBoost 训练完成: n=%d, pos=%d (%.1f%%), best_iter=%d, auc=%.4f, f1=%.4f, val_auc=%.4f, val_f1=%.4f",
        n, n_pos, 100 * pos_ratio, best_iter, auc, f1,
        val_metrics.get("val_auc", 0), val_metrics.get("val_f1", 0),
    )

    metrics = {
        "n_train": n, "n_pos": n_pos, "n_neg": n_neg,
        "pos_ratio": round(pos_ratio, 4),
        "scale_pos_weight": round(scale_pos_weight, 4),
        "best_iteration": int(best_iter),
        "accuracy": round(accuracy, 4),
        "f1": round(float(f1), 4),
        "auc": round(float(auc), 4),
        "model_path": save_path,
    }
    metrics.update(val_metrics)

    if return_model:
        return metrics, booster
    return metrics


# 启动时自动加载
def _schedule_load():
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(load_model))
    except RuntimeError:
        load_model()


_schedule_load()


# ============================================================
# Demo: 模型推理 + 概率校准演示
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("银行风控 XGBoost — 模型推理 + 概率校准")
    print("=" * 60)

    print(f"\n[1] 特征维度: {len(FEATURE_COLUMNS)} 维")
    print(f"  模型加载状态: is_model_loaded() = {is_model_loaded()}")

    print("\n[2] P(拒绝) → 风险分 校准 (sigmoid, k=3):")
    print(f"  {'prob':<8} {'calibrated_score':<16} {'decision':<10}")
    for p in [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.85, 0.95, 1.0]:
        score = ml_prob_to_risk_score(p)
        print(f"  {p:<8} {score:<16} {_prob_to_decision(p):<10}")

    print("\n[3] 训练接口签名:")
    import inspect
    sig = inspect.signature(train_and_save)
    print(f"  train_and_save{sig}")
    print(f"  30 维特征 → XGBoost 二分类 → P(拒绝) → sigmoid 校准 → 双轨融合")
