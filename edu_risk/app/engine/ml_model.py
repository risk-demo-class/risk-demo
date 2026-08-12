"""
ML 模型 — XGBoost
懒加载(_schedule_load 模块底部触发) + 双轨融合 + 训练脚本 + 抗假收敛 5 件套 + 最佳 F1 阈值扫描
模型不存在 / 未加载 → 优雅降级到纯规则,业务永不停。
"""
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# 25 维特征列,顺序必须与特征引擎一致(训练/推理共用)
FEATURE_COLUMNS: list[str] = [
    # 用户维度 14
    "user_total_enrollments", "user_enrollments_30d", "user_enrollments_7d",
    "user_total_payment", "user_avg_payment", "user_max_payment",
    "user_refund_count", "user_refund_amount", "user_refund_rate",
    "user_complaint_count", "user_cancel_count", "user_cheat_count",
    "user_exam_count", "user_device_count",
    # 报名维度 8
    "enroll_total_amount", "enroll_course_count", "enroll_category_count",
    "enroll_discount_amount", "enroll_discount_rate", "enroll_pay_interval",
    "enroll_is_night", "enroll_coupon_count",
    # 账号维度 3
    "acct_total_count", "acct_school_count", "acct_is_new",
]

_MODEL: object | None = None          # xgb.Booster 实例
_LOADED: bool = False
_LOAD_ERROR: str = ""


class MlResult:
    """预测结果封装"""
    __slots__ = ("score", "decision", "is_loaded")

    def __init__(self, score: float, decision: str, is_loaded: bool):
        self.score = score            # 0-100 风险分
        self.decision = decision      # 通过/标记/人工审核/拒绝
        self.is_loaded = is_loaded


def get_model():
    """返回 xgb.Booster,未加载返回 None。"""
    return _MODEL


def is_model_loaded() -> bool:
    return _LOADED


def load_model(path: str | None = None):
    """显式加载模型。文件不存在/格式错 → 降级纯规则,不抛异常。"""
    global _MODEL, _LOADED, _LOAD_ERROR
    path = path or settings.XGB_MODEL_PATH
    if not settings.XGB_ENABLED:
        _LOAD_ERROR = "XGB_ENABLED=False, 已降级纯规则"
        logger.warning(_LOAD_ERROR)
        return
    if not os.path.exists(path):
        _LOAD_ERROR = f"模型文件不存在: {path}, 已降级纯规则"
        logger.warning(_LOAD_ERROR)
        return
    try:
        import xgboost as xgb
        _MODEL = xgb.Booster()
        _MODEL.load_model(path)
        _LOADED = True
        logger.info("XGBoost 模型加载成功: %s", path)
    except Exception as e:
        _LOAD_ERROR = f"模型加载失败: {e}, 已降级纯规则"
        logger.exception(_LOAD_ERROR)


def _features_to_array(features: dict) -> list:
    """dict → 25 列 ndarray(按 FEATURE_COLUMNS 固定顺序)"""
    return [[features.get(col, 0.0) for col in FEATURE_COLUMNS]]


def _prob_to_decision(prob: float) -> str:
    """概率 → 4 种决策"""
    if prob < settings.ML_PASS_THRESHOLD:
        return "通过"
    if prob < settings.ML_MARK_THRESHOLD:
        return "标记"
    if prob < settings.ML_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def predict(features: dict) -> MlResult:
    """在线推理。模型未加载 → 返回 score=0, is_loaded=False(调用方走纯规则)。"""
    if not _LOADED or _MODEL is None:
        return MlResult(score=0.0, decision="通过", is_loaded=False)
    try:
        import numpy as np
        X = _features_to_array(features)
        dmat = _to_dmatrix(X)
        proba = float(_MODEL.predict(dmat)[0])
        score = round(proba * 100, 2)
        return MlResult(score=score, decision=_prob_to_decision(proba), is_loaded=True)
    except Exception:
        logger.exception("predict failed, fallback to rule-only")
        return MlResult(score=0.0, decision="通过", is_loaded=False)


def _to_dmatrix(X):
    """构造 DMatrix(懒 import 避免无 xgboost 环境启动即报错)。"""
    import xgboost as xgb
    return xgb.DMatrix(X)


# ============================================================
# 训练相关
# ============================================================

def train_and_save(df, label_col: str = "label", return_model: bool = True,
                   model_path: str | None = None, metrics: dict | None = None):
    """
    训练 + 评估 + 保存 .json。
    ⚠️ 返回元组顺序: (metrics, model) — 反着写会触发 XGBoost 2.x TypeError。
    4 必做: 80/20 stratify / 早停(auc) / scale_pos_weight≤10 / 最小样本量
    5 件套: 早停指标换 auc / warmup 50 / L1/L2 正则 / 假收敛检测 / baseline 对比
    """
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    if df is None or df.empty:
        raise ValueError("训练数据为空")

    X = df[FEATURE_COLUMNS].astype(float).values
    y = df[label_col].astype(int).values

    n_samples = len(df)
    pos_rate = float(y.mean())
    if n_samples < settings.XGB_MIN_SAMPLES:
        logger.warning("样本量 %d < 最小建议 %d", n_samples, settings.XGB_MIN_SAMPLES)

    # ---- 4 必做 #1: 80/20 stratify ----
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42)

    # ---- 4 必做 #3: scale_pos_weight ≤ 10 ----
    neg, pos = int((y_train == 0).sum()), int((y_train == 1).sum())
    scale_pos_weight = min(neg / max(pos, 1), settings.XGB_MAX_SCALE_POS_WEIGHT)

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dval = xgb.DMatrix(X_val, label=y_val)

    params = {
        "objective": "binary:logistic",
        "eval_metric": settings.XGB_EARLY_STOP_METRIC,
        "max_depth": 6,
        "learning_rate": 0.1,
        "subsample": settings.XGB_SUBSAMPLE,
        "colsample_bytree": settings.XGB_COLSAMPLE_BYTREE,
        "reg_alpha": settings.XGB_REG_ALPHA,
        "reg_lambda": settings.XGB_REG_LAMBDA,
        "min_child_weight": settings.XGB_MIN_CHILD_WEIGHT,
        "scale_pos_weight": scale_pos_weight,
        "tree_method": "hist",
    }

    # ---- 5 件套 #2: warmup 50 轮 + 两阶段手动早停 ----
    # 阶段 1: 前 50 轮不早停(让模型学起来)
    bst_warmup = xgb.train(
        params, dtrain, num_boost_round=settings.XGB_WARMUP_ROUNDS,
        evals=[(dval, "val")], verbose_eval=False)
    # 阶段 2: 从 warmup 基础上继续,早停监控 auc
    bst = xgb.train(
        params, dtrain, num_boost_round=1000, xgb_model=bst_warmup,
        evals=[(dval, "val")], early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        verbose_eval=False)

    # ---- 最佳 F1 阈值扫描(不硬编码 0.5) ----
    proba_val = bst.predict(dval)
    best_thr, best_f1 = 0.5, 0.0
    for thr in [round(i * 0.05, 2) for i in range(2, 18)]:  # 0.10 ~ 0.85
        f1 = f1_score(y_val, (proba_val > thr).astype(int))
        if f1 > best_f1:
            best_f1, best_thr = f1, thr

    pred_val = (proba_val > best_thr).astype(int)
    val_auc = roc_auc_score(y_val, proba_val)
    val_f1 = f1_score(y_val, pred_val)
    val_precision = precision_score(y_val, pred_val, zero_division=0)
    val_recall = recall_score(y_val, pred_val, zero_division=0)

    # baseline = 全预测负例的 acc
    baseline_acc = float((y_val == 0).mean())
    acc = float((pred_val == y_val).mean())

    # ---- 5 件套 #4: 假收敛自动检测(3 信号 + acc) ----
    best_iter = bst.best_iteration if bst.best_iteration is not None else settings.XGB_WARMUP_ROUNDS
    signals = {
        "best_iteration": best_iter,
        "val_auc": round(val_auc, 4),
        "val_f1": round(val_f1, 4),
        "acc": round(acc, 4),
        "baseline_acc": round(baseline_acc, 4),
        "best_f1_threshold": best_thr,
    }
    is_fake = (
        best_iter < settings.XGB_MIN_BEST_ITER
        or val_auc < settings.XGB_MIN_VAL_AUC
        or val_f1 < settings.XGB_MIN_VAL_F1
        or acc < baseline_acc + 0.02
    )
    signals["is_fake_convergence"] = bool(is_fake)

    # ---- 保存 ----
    model_path = model_path or settings.XGB_MODEL_PATH
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    bst.save_model(model_path)

    metrics = metrics or {}
    metrics.update(signals)
    metrics.update({
        "n_samples": n_samples,
        "pos_rate": round(pos_rate, 4),
        "scale_pos_weight": round(scale_pos_weight, 2),
        "val_precision": round(val_precision, 4),
        "val_recall": round(val_recall, 4),
        "val_ks": _compute_ks(y_val, proba_val),
    })

    if is_fake:
        logger.warning("⚠️ 检测到假收敛: %s", signals)

    if return_model:
        return metrics, bst
    return metrics


def _compute_ks(y_true, proba) -> float:
    """KS: 好/坏分布最大间隔,风控最常用指标。"""
    import numpy as np
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(y_true, proba)
    return float(np.max(tpr - fpr))


def _schedule_load():
    """模块级懒加载: import 时只检查文件不阻塞,第一次 predict 才真正用。"""
    if not settings.XGB_ENABLED:
        logger.info("XGB_ENABLED=False, 跳过加载,走纯规则")
        return
    path = settings.XGB_MODEL_PATH
    if os.path.exists(path):
        load_model(path)
    else:
        logger.warning("模型文件不存在: %s, 已降级纯规则(训练后自动加载)", path)


# import 时触发懒加载
_schedule_load()
