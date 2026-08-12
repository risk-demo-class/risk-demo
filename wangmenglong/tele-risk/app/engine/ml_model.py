"""
XGBoost 模型管理: 加载 / 推理 / 训练 / 兜底 (参照 ai_risk, 特征改为电信 25 维).

【重要约定】
  - 特征顺序固定 (FEATURE_COLUMNS), 跟 feature.py 算出的 25 个 key 一一对应
  - 标签二分类: 0=正常号卡, 1=高风险号卡 (GOIP/猫池/一证多卡/国际诈骗/物联网滥用)
  - 概率输出: predict_proba[:, 1] 即 P(高风险)
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

logger = logging.getLogger(__name__)


# 固定 30 维特征顺序 (训练和推理都用这个顺序, 防 dict 顺序不一致导致特征错位)
# 改这个列表前必须同步: feature.py 的 7 个 compute_*_features / train_xgb_model.py
FEATURE_COLUMNS: list[str] = [
    # 号卡 (5)
    "card_age_days",
    "card_is_iot",
    "card_intl_enabled",
    "card_roam_type_code",
    "card_status_normal",
    # 客户 (5)
    "cust_card_count",
    "cust_id_multi_card_flag",
    "cust_face_verify_passed",
    "cust_risk_tag_high_flag",
    "cust_open_channel_count",
    # 通信行为 (9)
    "cdr_out_count_1h",
    "cdr_out_count_24h",
    "cdr_in_count_24h",
    "cdr_distinct_cell_1h",
    "cdr_short_call_ratio",
    "cdr_intl_incoming_24h",
    "cdr_night_call_ratio",
    "cdr_avg_duration_sec",
    "cdr_night_call_count",
    # 设备 (3)
    "dev_cards_on_imei",
    "dev_card_imei_mismatch_flag",
    "dev_binding_changes_30d",
    # 渠道 (2)
    "channel_open_count_1h",
    "channel_is_agent_flag",
    # 物联网 (2)
    "iot_data_burst_ratio",
    "iot_card_device_unbound_flag",
    # 账单 (2)
    "bill_recharge_count_1h",
    "bill_outflow_ratio",
    # 集团 (2)
    "grp_sub_count",
    "grp_sub_abnormal_flag",
]

assert len(FEATURE_COLUMNS) == 30, f"特征数量必须是 30, 当前 {len(FEATURE_COLUMNS)}"


@dataclass
class MlResult:
    """XGBoost 单次推理结果"""
    score: float           # P(高风险) ∈ [0, 1]
    decision: str          # 4 档: 通过/标记/人工审核/拒绝
    is_loaded: bool        # 模型是否加载成功 (False 表示走兜底)


# 训练/推理全局单例
_MODEL: Optional[xgb.Booster] = None
_LOADED: bool = False


def get_model() -> Optional[xgb.Booster]:
    return _MODEL


def is_model_loaded() -> bool:
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
    """25 维 dict → numpy 数组 (1×25). 缺失用 0.0 兜底; None/字符串统一 float."""
    row = []
    for col in FEATURE_COLUMNS:
        v = features.get(col, 0.0)
        try:
            row.append(float(v))
        except (TypeError, ValueError):
            row.append(0.0)
    return np.array([row], dtype=np.float32)


def predict(features: dict) -> MlResult:
    """推理入口: 25 维特征 → P(高风险) + ML 维度决策. 模型没加载 → 兜底 score=0 通过."""
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
    """XGBoost 概率 P(高风险) ∈ [0,1] → 4 档决策 (用 config 里 ML_*_THRESHOLD)."""
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
    """训练 XGBoost 二分类器 + 评估 + 保存 (参照 ai_risk, 含防假收敛).

    - 不平衡数据: scale_pos_weight=neg/pos, 取 XGB_MAX_SCALE_POS_WEIGHT 上限
    - 80/20 stratify 拆分 + 早停 (验证集 auc 连续 N 轮不升就停) + warmup 防假收敛
    - 验证集 F1 阈值扫描 (0.10-0.85 找最佳), 输出 val_auc + val_f1
    """
    n = len(y)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    pos_ratio = n_pos / n if n else 0.0

    if n < settings.XGB_MIN_SAMPLES:
        logger.warning(
            "样本量 %d < 推荐最小 %d (25 维 × 50 倍经验值), 模型可能欠拟合, "
            "建议继续积累号卡数据后重训", n, settings.XGB_MIN_SAMPLES,
        )

    raw_scale = n_neg / n_pos if n_pos > 0 else 1.0
    scale_pos_weight = min(raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT)
    if raw_scale > settings.XGB_MAX_SCALE_POS_WEIGHT:
        logger.warning(
            "scale_pos_weight %.2f 超过上限 %.2f, 已截断到 %.2f",
            raw_scale, settings.XGB_MAX_SCALE_POS_WEIGHT, scale_pos_weight,
        )

    if pos_ratio < settings.XGB_MIN_POS_RATIO:
        logger.warning(
            "正例比例 %.1f%% < 推荐最小 %.0f%%, 模型可能假收敛",
            100 * pos_ratio, 100 * settings.XGB_MIN_POS_RATIO,
        )

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

    # warmup 防假收敛: 前 N 轮不让早停
    if esr and len(eval_set) > 1 and settings.XGB_WARMUP_ROUNDS > 0:
        warmup_params = {**params, "eval_metric": ["logloss"]}
        warmup_booster = xgb.train(
            warmup_params, dtrain,
            num_boost_round=settings.XGB_WARMUP_ROUNDS,
            evals=eval_set, verbose_eval=False,
        )
        booster = xgb.train(
            params, dtrain,
            num_boost_round=num_boost_round,
            evals=eval_set,
            early_stopping_rounds=esr,
            xgb_model=warmup_booster,
            verbose_eval=False,
        )
    else:
        booster = xgb.train(
            params, dtrain,
            num_boost_round=num_boost_round,
            evals=eval_set,
            early_stopping_rounds=esr if len(eval_set) > 1 else None,
            verbose_eval=False,
        )

    # 全量评估
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
        # 验证集 F1 阈值扫描
        best_f1, best_thr = 0.0, 0.5
        for thr in [round(x * 0.01, 2) for x in range(10, 90, 5)]:
            y_val_pred_t = (y_val_pred_prob >= thr).astype(int)
            f1_t = f1_score(y_val, y_val_pred_t, zero_division=0)
            if f1_t > best_f1:
                best_f1 = f1_t
                best_thr = thr
        y_val_pred = (y_val_pred_prob >= best_thr).astype(int)
        val_acc = float(np.mean(y_val_pred == y_val))
        val_auc = roc_auc_score(y_val, y_val_pred_prob) if len(np.unique(y_val)) > 1 else 0.0
        val_metrics = {
            "n_val": int(len(y_val)),
            "val_accuracy": round(val_acc, 4),
            "val_f1": round(float(best_f1), 4),
            "val_auc": round(float(val_auc), 4),
            "best_f1_threshold": round(best_thr, 2),
        }

    # 保存
    if model_path:
        save_path = model_path
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        save_path = str(project_root / settings.XGB_MODEL_PATH)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    booster.save_model(save_path)

    best_iter = booster.best_iteration if hasattr(booster, "best_iteration") and booster.best_iteration is not None else num_boost_round
    logger.info(
        "XGBoost 已保存: %s, n=%d, pos=%d (%.1f%%), neg=%d, scale=%.2f, best_iter=%d, acc=%.4f, auc=%.4f, f1=%.4f",
        save_path, n, n_pos, 100 * pos_ratio, n_neg, scale_pos_weight,
        best_iter, accuracy, auc, f1,
    )

    # 假收敛检测
    is_fake = False
    if best_iter < settings.XGB_MIN_BEST_ITER:
        logger.warning("[假收敛嫌疑] best_iter=%d < %d", best_iter, settings.XGB_MIN_BEST_ITER)
        is_fake = True
    if val_metrics and val_metrics.get("val_auc", 0) < settings.XGB_MIN_VAL_AUC:
        logger.warning("[质量不达标] val_auc=%.4f < %.2f", val_metrics["val_auc"], settings.XGB_MIN_VAL_AUC)
        is_fake = True
    if val_metrics and val_metrics.get("val_f1", 0) < settings.XGB_MIN_VAL_F1:
        logger.warning("[质量不达标] val_f1=%.4f < %.2f", val_metrics["val_f1"], settings.XGB_MIN_VAL_F1)

    metrics = {
        "n_train": n, "n_pos": n_pos, "n_neg": n_neg,
        "pos_ratio": round(pos_ratio, 4),
        "scale_pos_weight": round(scale_pos_weight, 4),
        "raw_scale_pos_weight": round(raw_scale, 4),
        "best_iteration": int(best_iter),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(float(f1), 4),
        "auc": round(float(auc), 4),
        "model_path": save_path,
        "baseline_accuracy": round(n_neg / n if n else 0.0, 4),
        "is_fake_convergence": is_fake,
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


if __name__ == "__main__":
    print("=" * 60)
    print("XGBoost 模型管理 — 电信 25 维特征")
    print("=" * 60)
    print(f"  FEATURE_COLUMNS 长度 = {len(FEATURE_COLUMNS)} (必须 25)")
    print(f"  模型路径 = {settings.XGB_MODEL_PATH}")
    print(f"  is_loaded = {is_model_loaded()}")
    # 推理兜底演示
    sample = {col: 0.0 for col in FEATURE_COLUMNS}
    sample["cdr_out_count_1h"] = 30
    sample["dev_cards_on_imei"] = 5
    res = predict(sample)
    print(f"  predict 兜底 (未加载): score={res.score}, decision={res.decision}")
    print("=" * 60)
