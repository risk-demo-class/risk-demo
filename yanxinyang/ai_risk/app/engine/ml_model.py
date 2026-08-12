# -*- coding: utf-8 -*-
"""XGBoost 模型层 —— 对应教学宝典《第 7 章：XGBoost 模型》

🛂 类比：资深安检员（看眼神、走路姿态）—— 从历史案例学经验。

一句话定义（宝典 7.1）：**XGBoost = 一棵一棵"纠错"的决策树**。
    第 1 棵：初始预测 → 第 2~N 棵：残差拟合 → 梯度提升（二阶导数）

────────────────────────────────────────────────────────────────────────
本文件实现宝典 7.5 的 9 个关键函数，并落地全部工程要求：
    ✅ 懒加载 `_schedule_load()`（import 时检查文件、零阻塞）
    ✅ 5 个关键参数（7.3）+ 4 个工程优化（7.4：Histogram / 稀疏感知 / 缓存友好 / 分块）
    ✅ 训练 4 必做（7.7：80/20 stratify + 早停 + scale_pos_weight≤10 + 最小样本 1250）
    ✅ 5 件套抗假收敛（7.7：早停指标 auc + warmup 50 + L1/L2 正则 + 3 信号检测 + baseline 对比）
    ✅ 最佳 F1 阈值扫描（7.8：0.10~0.85 步长 0.05）
    ✅ 评估 5 指标（7.8：AUC / KS / Precision / Recall / F1）
    ✅ 3 种特征重要性（7.9：weight / gain / 路径贡献法近似 SHAP）
    ✅ 概率 → 4 种决策（7.10）
    ✅ 降级优雅（7.6：模型不存在 → 纯规则，业务永不停）

关于实现方式：环境不允许安装第三方包，因此这里用标准库**同构实现** XGBoost 的
核心算法（二阶泰勒展开 + 直方图分裂 + 稀疏感知默认方向 + L1/L2 正则）。
若运行环境已安装原生 `xgboost`，`_NATIVE_AVAILABLE` 为 True 时自动走原生 Booster，
两条路径共用同一套指标/阈值/降级逻辑。
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import settings
from app.engine.feature import FEATURE_NAMES

logger = logging.getLogger("ai_risk.engine.ml_model")

#: 宝典 5.3 / FAQ 12：加特征必须同步这里，否则 XGBoost 不生效
FEATURE_COLUMNS: List[str] = list(FEATURE_NAMES)

try:  # 原生 XGBoost 可选直通
    import xgboost as _xgb  # type: ignore

    _NATIVE_AVAILABLE = True
    _NATIVE_VERSION = getattr(_xgb, "__version__", "unknown")
except Exception:  # noqa: BLE001
    _xgb = None  # type: ignore
    _NATIVE_AVAILABLE = False
    _NATIVE_VERSION = ""

MISSING = float("nan")


# ====================================================================== 结果封装
@dataclass
class MlResult:
    """宝典 7.5 的 `MlResult` 类：预测结果封装。"""

    score: float = 0.0            # 0-100（= probability × 100）
    probability: float = 0.0      # 原始概率
    decision: str = "通过"        # 4 种决策之一
    is_loaded: bool = False       # 模型是否已加载（未加载 → 纯规则降级）
    reason: str = ""
    contributions: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"score": round(self.score, 2), "probability": round(self.probability, 6),
                "decision": self.decision, "is_loaded": self.is_loaded, "reason": self.reason}


# ====================================================================== 树结构
@dataclass
class TreeNode:
    leaf: bool = False
    value: float = 0.0            # 叶子权重
    feature: int = -1             # 分裂特征索引
    threshold: float = 0.0        # 分裂阈值
    default_left: bool = True     # 稀疏感知：缺失值默认方向（宝典 7.4）
    gain: float = 0.0
    cover: float = 0.0
    left: Optional["TreeNode"] = None
    right: Optional["TreeNode"] = None

    def to_dict(self) -> Dict[str, Any]:
        if self.leaf:
            return {"leaf": round(self.value, 6), "cover": round(self.cover, 4)}
        return {"f": self.feature, "t": round(self.threshold, 6), "dl": self.default_left,
                "gain": round(self.gain, 4), "cover": round(self.cover, 4),
                "l": self.left.to_dict() if self.left else None,
                "r": self.right.to_dict() if self.right else None}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TreeNode":
        if "leaf" in data:
            return TreeNode(leaf=True, value=float(data["leaf"]), cover=float(data.get("cover", 0)))
        return TreeNode(leaf=False, feature=int(data["f"]), threshold=float(data["t"]),
                        default_left=bool(data.get("dl", True)), gain=float(data.get("gain", 0)),
                        cover=float(data.get("cover", 0)),
                        left=TreeNode.from_dict(data["l"]), right=TreeNode.from_dict(data["r"]))


@dataclass
class Booster:
    """纯 Python Booster —— 与 xgb.Booster 同构（predict / save_model / load_model）。"""

    trees: List[TreeNode] = field(default_factory=list)
    base_score: float = 0.0                    # logit 空间的初始预测
    learning_rate: float = 0.1
    feature_columns: List[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    best_iteration: int = 0
    best_f1_threshold: float = 0.5
    metrics: Dict[str, Any] = field(default_factory=dict)
    impl: str = "pure_python_gbdt"
    trained_at: str = ""

    # ---------------------------------------------------------- 推理
    def raw_margin(self, row: Sequence[float], n_trees: Optional[int] = None) -> float:
        total = self.base_score
        trees = self.trees if n_trees is None else self.trees[:n_trees]
        for tree in trees:
            total += self.learning_rate * _walk(tree, row)
        return total

    def predict_proba(self, row: Sequence[float], n_trees: Optional[int] = None) -> float:
        return _sigmoid(self.raw_margin(row, n_trees))

    # ---------------------------------------------------------- 持久化（官方 JSON 风格）
    def to_json(self) -> Dict[str, Any]:
        return {
            "learner": {"impl": self.impl, "objective": "binary:logistic",
                        "base_score": self.base_score, "learning_rate": self.learning_rate,
                        "feature_names": self.feature_columns,
                        "best_iteration": self.best_iteration,
                        "best_f1_threshold": self.best_f1_threshold,
                        "trained_at": self.trained_at},
            "metrics": self.metrics,
            "trees": [t.to_dict() for t in self.trees],
        }

    def save_model(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(self.to_json(), fp, ensure_ascii=False)
        logger.info("模型已保存: %s（%d 棵树）", path, len(self.trees))

    @staticmethod
    def load(path: str) -> "Booster":
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        learner = data.get("learner", {})
        return Booster(
            trees=[TreeNode.from_dict(t) for t in data.get("trees", [])],
            base_score=float(learner.get("base_score", 0.0)),
            learning_rate=float(learner.get("learning_rate", 0.1)),
            feature_columns=list(learner.get("feature_names") or FEATURE_COLUMNS),
            best_iteration=int(learner.get("best_iteration", 0)),
            best_f1_threshold=float(learner.get("best_f1_threshold", 0.5)),
            metrics=data.get("metrics", {}),
            impl=str(learner.get("impl", "pure_python_gbdt")),
            trained_at=str(learner.get("trained_at", "")),
        )


def _walk(node: TreeNode, row: Sequence[float]) -> float:
    while not node.leaf:
        value = row[node.feature] if node.feature < len(row) else MISSING
        if value is None or (isinstance(value, float) and math.isnan(value)):
            node = node.left if node.default_left else node.right   # 稀疏感知
        elif value < node.threshold:
            node = node.left                                        # type: ignore[assignment]
        else:
            node = node.right                                       # type: ignore[assignment]
        if node is None:                                            # 防御
            return 0.0
    return node.value


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-min(x, 60.0)))
    exp_x = math.exp(max(x, -60.0))
    return exp_x / (1.0 + exp_x)


# ====================================================================== 全局状态（懒加载）
_model: Optional[Booster] = None
_native_booster: Any = None
_LOADED = False
_LOAD_ERROR = ""
_LOAD_TIME = ""


def get_model() -> Optional[Booster]:
    """宝典 7.5：返回 Booster。"""
    return _model


def is_model_loaded() -> bool:
    """宝典 7.5：布尔，模型是否已加载（决策时用于降级判断）。"""
    return _LOADED


def model_status() -> Dict[str, Any]:
    """给 /api/model/status。"""
    info: Dict[str, Any] = {
        "enabled": settings.XGB_ENABLED,
        "loaded": _LOADED,
        "model_path": settings.XGB_MODEL_PATH,
        "model_exists": os.path.exists(settings.XGB_MODEL_PATH),
        "load_error": _LOAD_ERROR,
        "load_time": _LOAD_TIME,
        "native_xgboost": _NATIVE_AVAILABLE,
        "native_version": _NATIVE_VERSION,
        "implementation": "原生 XGBoost Booster" if _native_booster is not None
                          else ("纯 Python 同构 GBDT" if _LOADED else "未加载（降级为纯规则）"),
        "feature_columns": FEATURE_COLUMNS,
        "feature_count": len(FEATURE_COLUMNS),
        "params": {
            "n_estimators": settings.XGB_N_ESTIMATORS, "max_depth": settings.XGB_MAX_DEPTH,
            "learning_rate": settings.XGB_LEARNING_RATE, "subsample": settings.XGB_SUBSAMPLE,
            "colsample_bytree": settings.XGB_COLSAMPLE_BYTREE,
            "reg_alpha": settings.XGB_REG_ALPHA, "reg_lambda": settings.XGB_REG_LAMBDA,
            "min_child_weight": settings.XGB_MIN_CHILD_WEIGHT,
            "early_stopping_rounds": settings.XGB_EARLY_STOPPING_ROUNDS,
            "early_stop_metric": settings.XGB_EARLY_STOP_METRIC,
            "warmup_rounds": settings.XGB_WARMUP_ROUNDS,
            "max_scale_pos_weight": settings.XGB_MAX_SCALE_POS_WEIGHT,
        },
        "decision_thresholds": {
            "通过": f"< {settings.ML_PASS_THRESHOLD}",
            "标记": f"{settings.ML_PASS_THRESHOLD} ~ {settings.ML_MARK_THRESHOLD}",
            "人工审核": f"{settings.ML_MARK_THRESHOLD} ~ {settings.ML_REVIEW_THRESHOLD}",
            "拒绝": f">= {settings.ML_REVIEW_THRESHOLD}",
        },
    }
    if _model is not None:
        info.update({"trees": len(_model.trees), "best_iteration": _model.best_iteration,
                     "best_f1_threshold": _model.best_f1_threshold,
                     "trained_at": _model.trained_at, "metrics": _model.metrics})
    return info


def load_model(path: Optional[str] = None) -> bool:
    """宝典 7.5：显式加载。"""
    global _model, _native_booster, _LOADED, _LOAD_ERROR, _LOAD_TIME
    path = path or settings.XGB_MODEL_PATH
    if not os.path.exists(path):
        _LOAD_ERROR = f"模型文件不存在: {path}"
        _LOADED = False
        return False
    try:
        with open(path, "r", encoding="utf-8") as fp:
            head = json.load(fp)
        if head.get("learner", {}).get("impl") == "pure_python_gbdt":
            _model = Booster.load(path)
            _native_booster = None
        elif _NATIVE_AVAILABLE:                       # 原生 Booster JSON
            booster = _xgb.Booster()                  # type: ignore[union-attr]
            booster.load_model(path)
            _native_booster = booster
            _model = None
        else:
            raise ValueError("模型文件是原生 XGBoost 格式，但当前环境未安装 xgboost")
        _LOADED = True
        _LOAD_ERROR = ""
        _LOAD_TIME = time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info("XGBoost 模型加载成功: %s", path)
        return True
    except Exception as exc:  # noqa: BLE001
        _model, _native_booster, _LOADED = None, None, False
        _LOAD_ERROR = f"加载失败: {exc}"
        logger.warning("XGBoost 模型加载失败，降级为纯规则: %s", exc)
        return False


def unload_model() -> None:
    global _model, _native_booster, _LOADED
    _model, _native_booster, _LOADED = None, None, False


def _features_to_array(features: Dict[str, float]) -> List[float]:
    """宝典 7.5：dict → 25 列 ndarray（此处为 list[float]，缺失值填 NaN 交给稀疏感知）。"""
    row: List[float] = []
    for name in FEATURE_COLUMNS:
        value = features.get(name)
        if value is None:
            row.append(MISSING)
            continue
        try:
            row.append(float(value))
        except (TypeError, ValueError):
            row.append(MISSING)
    return row


def _prob_to_decision(prob: float) -> str:
    """宝典 7.10：概率 → 4 种决策。"""
    if prob < settings.ML_PASS_THRESHOLD:
        return "通过"
    if prob < settings.ML_MARK_THRESHOLD:
        return "标记"
    if prob < settings.ML_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def predict(features: Dict[str, float], explain: bool = False) -> MlResult:
    """宝典 7.5：预测，返回 MlResult。模型未加载 → score=0 + is_loaded=False（降级）。"""
    if not settings.XGB_ENABLED:
        return MlResult(reason="XGB_ENABLED=False，走纯规则")
    if not _LOADED:
        return MlResult(reason=_LOAD_ERROR or "模型未加载，走纯规则")
    row = _features_to_array(features)
    try:
        if _native_booster is not None:
            dmatrix = _xgb.DMatrix([row], feature_names=FEATURE_COLUMNS)  # type: ignore[union-attr]
            prob = float(_native_booster.predict(dmatrix)[0])
        else:
            assert _model is not None
            prob = _model.predict_proba(row)
    except Exception as exc:  # noqa: BLE001
        logger.exception("模型推理失败，降级为纯规则")
        return MlResult(reason=f"推理异常降级: {exc}")

    prob = min(max(prob, 0.0), 1.0)
    result = MlResult(score=prob * 100.0, probability=prob, decision=_prob_to_decision(prob),
                      is_loaded=True, reason="XGBoost 推理成功")
    if explain and _model is not None:
        result.contributions = explain_prediction(features)
    return result


# ====================================================================== 3 种特征重要性（宝典 7.9）
def feature_importance() -> Dict[str, Any]:
    """weight（分裂次数）/ gain（平均增益）/ cover（样本覆盖）。"""
    if _model is None:
        return {"available": False, "reason": "模型未加载或为原生格式", "weight": [], "gain": []}
    weight: Dict[str, int] = {}
    gain_sum: Dict[str, float] = {}
    cover_sum: Dict[str, float] = {}

    def walk(node: TreeNode) -> None:
        if node.leaf:
            return
        name = FEATURE_COLUMNS[node.feature] if node.feature < len(FEATURE_COLUMNS) else f"f{node.feature}"
        weight[name] = weight.get(name, 0) + 1
        gain_sum[name] = gain_sum.get(name, 0.0) + node.gain
        cover_sum[name] = cover_sum.get(name, 0.0) + node.cover
        walk(node.left)   # type: ignore[arg-type]
        walk(node.right)  # type: ignore[arg-type]

    for tree in _model.trees:
        walk(tree)

    def rank(data: Dict[str, float], normalize: bool = False) -> List[Dict[str, Any]]:
        items = []
        for name, value in data.items():
            val = value / weight[name] if normalize and weight.get(name) else value
            items.append({"feature": name, "value": round(float(val), 4)})
        return sorted(items, key=lambda x: -x["value"])

    return {"available": True,
            "weight": rank({k: float(v) for k, v in weight.items()}),
            "gain": rank(gain_sum, normalize=True),
            "cover": rank(cover_sum, normalize=True),
            "shap_note": "SHAP 精确算法（TreeSHAP）未实现；下方「决策解释」用路径贡献法（Saabas）近似"}


def explain_prediction(features: Dict[str, float]) -> Dict[str, float]:
    """近似 SHAP：路径贡献法（Saabas）—— 沿决策路径把预测变化归因给分裂特征。"""
    if _model is None:
        return {}
    row = _features_to_array(features)
    contrib: Dict[str, float] = {}

    def expected(node: TreeNode) -> float:
        if node.leaf:
            return node.value
        left, right = node.left, node.right
        total = (left.cover if left else 0) + (right.cover if right else 0)
        if total <= 0:
            return 0.0
        return (expected(left) * (left.cover if left else 0)      # type: ignore[arg-type]
                + expected(right) * (right.cover if right else 0)) / total   # type: ignore[arg-type]

    for tree in _model.trees:
        node = tree
        parent_value = expected(node)
        while not node.leaf:
            value = row[node.feature]
            if value is None or math.isnan(value):
                child = node.left if node.default_left else node.right
            else:
                child = node.left if value < node.threshold else node.right
            child_value = expected(child)  # type: ignore[arg-type]
            name = FEATURE_COLUMNS[node.feature]
            contrib[name] = contrib.get(name, 0.0) + (child_value - parent_value) * _model.learning_rate
            parent_value = child_value
            node = child  # type: ignore[assignment]
    return {k: round(v, 6) for k, v in sorted(contrib.items(), key=lambda x: -abs(x[1]))}


# ====================================================================== 评估指标（宝典 7.8）
def _auc(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    pairs = sorted(zip(y_prob, y_true), key=lambda x: x[0])
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0            # 1-based 平均秩，处理并列
        for k in range(i, j + 1):
            if pairs[k][1] == 1:
                rank_sum += avg_rank
        i = j + 1
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _ks(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    """风控最常用指标：好坏人累计分布最大间隔。"""
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.0
    ordered = sorted(zip(y_prob, y_true), key=lambda x: -x[0])
    cum_pos = cum_neg = 0
    best = 0.0
    for _, label in ordered:
        if label == 1:
            cum_pos += 1
        else:
            cum_neg += 1
        best = max(best, abs(cum_pos / n_pos - cum_neg / n_neg))
    return best


def _prf(y_true: Sequence[int], y_pred: Sequence[int]) -> Tuple[float, float, float]:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def scan_best_f1_threshold(y_true: Sequence[int], y_prob: Sequence[float]) -> Tuple[float, float]:
    """宝典 7.8：最佳 F1 阈值扫描（0.10 → 0.85，步长 0.05）。绝不硬编码 0.5。"""
    best_threshold, best_f1 = 0.5, -1.0
    threshold = settings.XGB_THRESHOLD_SCAN_START
    while threshold <= settings.XGB_THRESHOLD_SCAN_END + 1e-9:
        pred = [1 if p > threshold else 0 for p in y_prob]
        _, _, f1 = _prf(y_true, pred)
        if f1 > best_f1:
            best_f1, best_threshold = f1, round(threshold, 4)
        threshold += settings.XGB_THRESHOLD_SCAN_STEP
    return best_threshold, max(best_f1, 0.0)


def evaluate(y_true: Sequence[int], y_prob: Sequence[float], threshold: float = 0.5) -> Dict[str, float]:
    pred = [1 if p > threshold else 0 for p in y_prob]
    precision, recall, f1 = _prf(y_true, pred)
    acc = sum(1 for t, p in zip(y_true, pred) if t == p) / max(len(y_true), 1)
    n_pos = sum(y_true)
    baseline_acc = max(n_pos, len(y_true) - n_pos) / max(len(y_true), 1)
    return {"acc": round(acc, 4), "baseline_acc": round(baseline_acc, 4),
            "auc": round(_auc(y_true, y_prob), 4), "ks": round(_ks(y_true, y_prob), 4),
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "threshold": round(threshold, 4), "pos": n_pos, "total": len(y_true)}


# ====================================================================== 训练
def _stratified_split(x: List[List[float]], y: List[int], test_size: float,
                      seed: int = 42) -> Tuple[List[List[float]], List[int], List[List[float]], List[int]]:
    """宝典 7.7 必做 ①：80/20 stratify 拆分 —— 保证验证集正负比 = 训练集。"""
    rng = random.Random(seed)
    idx_pos = [i for i, label in enumerate(y) if label == 1]
    idx_neg = [i for i, label in enumerate(y) if label == 0]
    rng.shuffle(idx_pos)
    rng.shuffle(idx_neg)
    n_pos_test = max(1, int(round(len(idx_pos) * test_size))) if idx_pos else 0
    n_neg_test = max(1, int(round(len(idx_neg) * test_size))) if idx_neg else 0
    test_idx = set(idx_pos[:n_pos_test] + idx_neg[:n_neg_test])
    x_train = [x[i] for i in range(len(x)) if i not in test_idx]
    y_train = [y[i] for i in range(len(y)) if i not in test_idx]
    x_val = [x[i] for i in sorted(test_idx)]
    y_val = [y[i] for i in sorted(test_idx)]
    return x_train, y_train, x_val, y_val


class _Histogram:
    """宝典 7.4 优化 ①：Histogram 分位数近似 —— 特征分桶，只对桶边界尝试分裂。"""

    def __init__(self, x: List[List[float]], max_bins: int = 32) -> None:
        self.n_features = len(FEATURE_COLUMNS)
        self.max_bins = max_bins
        self.edges: List[List[float]] = []
        self.binned: List[List[int]] = []       # 列存（缓存友好，宝典 7.4 优化 ③）
        for f in range(self.n_features):
            column = [row[f] for row in x]
            valid = sorted(v for v in column if not math.isnan(v))
            edges: List[float] = []
            if valid:
                step = max(1, len(valid) // max_bins)
                seen = set()
                for i in range(step, len(valid), step):
                    value = valid[i]
                    if value not in seen:
                        seen.add(value)
                        edges.append(value)
            self.edges.append(edges)
            self.binned.append([self._bin(value, edges) for value in column])

    @staticmethod
    def _bin(value: float, edges: List[float]) -> int:
        if math.isnan(value):
            return -1                            # -1 = 缺失（稀疏感知，宝典 7.4 优化 ②）
        low, high = 0, len(edges)
        while low < high:
            mid = (low + high) // 2
            if value < edges[mid]:
                high = mid
            else:
                low = mid + 1
        return low

    def n_bins(self, feature: int) -> int:
        return len(self.edges[feature]) + 1

    def threshold(self, feature: int, bin_idx: int) -> float:
        edges = self.edges[feature]
        if not edges:
            return 0.0
        return edges[min(max(bin_idx, 0), len(edges) - 1)]


def _build_tree(hist: _Histogram, rows: List[int], grad: List[float], hess: List[float],
                depth: int, params: Dict[str, Any], features: List[int],
                rng: random.Random) -> TreeNode:
    g_sum = sum(grad[i] for i in rows)
    h_sum = sum(hess[i] for i in rows)
    reg_lambda = params["reg_lambda"]
    reg_alpha = params["reg_alpha"]

    def leaf_weight(g: float, h: float) -> float:
        """L1(reg_alpha) 软阈值 + L2(reg_lambda) 收缩 —— XGBoost 叶子权重闭式解。"""
        numerator = -g
        if numerator > reg_alpha:
            numerator -= reg_alpha
        elif numerator < -reg_alpha:
            numerator += reg_alpha
        else:
            numerator = 0.0
        return numerator / (h + reg_lambda)

    node_score = (g_sum ** 2) / (h_sum + reg_lambda) if (h_sum + reg_lambda) else 0.0

    if depth >= params["max_depth"] or len(rows) < 2 * params["min_child_weight"]:
        return TreeNode(leaf=True, value=leaf_weight(g_sum, h_sum), cover=h_sum)

    best = {"gain": 0.0, "feature": -1, "bin": 0, "default_left": True}
    for feature in features:
        n_bins = hist.n_bins(feature)
        if n_bins <= 1:
            continue
        binned = hist.binned[feature]
        g_bins = [0.0] * n_bins
        h_bins = [0.0] * n_bins
        g_missing = h_missing = 0.0
        for i in rows:                                  # 单趟扫描填直方图
            b = binned[i]
            if b < 0:
                g_missing += grad[i]
                h_missing += hess[i]
            else:
                g_bins[b] += grad[i]
                h_bins[b] += hess[i]
        g_left = h_left = 0.0
        for b in range(n_bins - 1):
            g_left += g_bins[b]
            h_left += h_bins[b]
            for default_left in (True, False):          # 稀疏感知：缺失值往左/往右都试
                gl = g_left + (g_missing if default_left else 0.0)
                hl = h_left + (h_missing if default_left else 0.0)
                gr, hr = g_sum - gl, h_sum - hl
                if hl < params["min_child_weight"] or hr < params["min_child_weight"]:
                    continue
                gain = 0.5 * ((gl ** 2) / (hl + reg_lambda) + (gr ** 2) / (hr + reg_lambda)
                              - node_score) - params["gamma"]
                if gain > best["gain"]:
                    best = {"gain": gain, "feature": feature, "bin": b, "default_left": default_left}

    if best["feature"] < 0 or best["gain"] <= 1e-8:
        return TreeNode(leaf=True, value=leaf_weight(g_sum, h_sum), cover=h_sum)

    feature = int(best["feature"])
    threshold = hist.threshold(feature, int(best["bin"]) + 1)
    default_left = bool(best["default_left"])
    binned = hist.binned[feature]
    left_rows, right_rows = [], []
    for i in rows:
        b = binned[i]
        if b < 0:
            (left_rows if default_left else right_rows).append(i)
        elif b <= best["bin"]:
            left_rows.append(i)
        else:
            right_rows.append(i)
    if not left_rows or not right_rows:
        return TreeNode(leaf=True, value=leaf_weight(g_sum, h_sum), cover=h_sum)

    return TreeNode(
        leaf=False, feature=feature, threshold=threshold, default_left=default_left,
        gain=float(best["gain"]), cover=h_sum,
        left=_build_tree(hist, left_rows, grad, hess, depth + 1, params, features, rng),
        right=_build_tree(hist, right_rows, grad, hess, depth + 1, params, features, rng),
    )


def train_and_save(x: List[List[float]], y: List[int], model_path: Optional[str] = None,
                   return_model: bool = False, log: Optional[Any] = None,
                   n_estimators: Optional[int] = None,
                   seed: int = 42) -> Any:
    """训练 + 评估 + 保存 .json（宝典 7.5）。

    ⚠️ 返回元组顺序是 **(metrics, model)**，不是 (model, metrics)。
       宝典 7.0/7.5 实战坑：反着写会触发 XGBoost 2.x
       `TypeError: Expecting <class 'int'> or <class 'slice'>. Got <class 'str'>`
    """
    def emit(msg: str) -> None:
        logger.info(msg)
        if log is not None:
            log(msg)

    model_path = model_path or settings.XGB_MODEL_PATH
    n_total = len(y)
    n_pos = sum(y)
    n_neg = n_total - n_pos
    metrics: Dict[str, Any] = {"n_samples": n_total, "n_pos": n_pos, "n_neg": n_neg,
                               "pos_ratio": round(n_pos / n_total, 4) if n_total else 0.0,
                               "warnings": [], "is_fake_convergence": False,
                               "fake_convergence_reasons": []}

    if n_total == 0 or n_pos == 0 or n_neg == 0:
        metrics["warnings"].append("训练数据缺少正样本或负样本，无法训练（FAQ 4：先跑 gen_risk_data.py）")
        metrics["is_fake_convergence"] = True
        metrics["fake_convergence_reasons"].append("单一类别数据")
        return (metrics, None) if return_model else metrics

    # ---- 必做 ④：最小样本量 1250 = 25 维 × 50
    if n_total < settings.XGB_MIN_SAMPLES:
        msg = (f"⚠️ 样本量 {n_total} < XGB_MIN_SAMPLES({settings.XGB_MIN_SAMPLES} = 25 维 × 50)，"
               f"模型可能欠拟合")
        metrics["warnings"].append(msg)
        emit(msg)

    # ---- 必做 ①：80/20 stratify
    x_train, y_train, x_val, y_val = _stratified_split(x, y, settings.XGB_TEST_SIZE, seed)
    emit(f"数据拆分: 训练 {len(y_train)}（正 {sum(y_train)}） / 验证 {len(y_val)}（正 {sum(y_val)}），"
         f"stratify=y test_size={settings.XGB_TEST_SIZE}")

    # ---- 必做 ③：scale_pos_weight ≤ 10.0
    raw_spw = (len(y_train) - sum(y_train)) / max(sum(y_train), 1)
    scale_pos_weight = min(raw_spw, settings.XGB_MAX_SCALE_POS_WEIGHT)
    metrics["scale_pos_weight_raw"] = round(raw_spw, 4)
    metrics["scale_pos_weight"] = round(scale_pos_weight, 4)
    if raw_spw > settings.XGB_MAX_SCALE_POS_WEIGHT:
        msg = (f"⚠️ scale_pos_weight 理论值 {raw_spw:.2f} 被截断到 "
               f"{settings.XGB_MAX_SCALE_POS_WEIGHT}（正例仅 {metrics['pos_ratio']:.1%}，"
               f"建议 gen_risk_data.py --target-pos-ratio 0.30 重造数据）")
        metrics["warnings"].append(msg)
        emit(msg)

    if _NATIVE_AVAILABLE:
        emit(f"检测到原生 xgboost {_NATIVE_VERSION}，但本教学实现统一使用同构 GBDT 以保证结果可复现")

    params = {
        "max_depth": settings.XGB_MAX_DEPTH,
        "min_child_weight": settings.XGB_MIN_CHILD_WEIGHT,
        "reg_alpha": settings.XGB_REG_ALPHA,        # ③ L1
        "reg_lambda": settings.XGB_REG_LAMBDA,      # ③ L2
        "gamma": 0.0,
    }
    n_estimators = n_estimators or settings.XGB_N_ESTIMATORS
    learning_rate = settings.XGB_LEARNING_RATE
    subsample = settings.XGB_SUBSAMPLE
    colsample = settings.XGB_COLSAMPLE_BYTREE
    rng = random.Random(seed)

    base_rate = sum(y_train) / len(y_train)
    base_score = math.log(base_rate / (1 - base_rate)) if 0 < base_rate < 1 else 0.0

    emit(f"参数: n_estimators={n_estimators} max_depth={params['max_depth']} lr={learning_rate} "
         f"subsample={subsample} colsample_bytree={colsample} "
         f"reg_alpha={params['reg_alpha']} reg_lambda={params['reg_lambda']} "
         f"min_child_weight={params['min_child_weight']}")
    emit(f"抗假收敛: 早停指标={settings.XGB_EARLY_STOP_METRIC} warmup={settings.XGB_WARMUP_ROUNDS} "
         f"early_stopping_rounds={settings.XGB_EARLY_STOPPING_ROUNDS}")

    hist = _Histogram(x_train, max_bins=32)
    n_train = len(y_train)
    margins = [base_score] * n_train
    val_margins = [base_score] * len(y_val)
    booster = Booster(base_score=base_score, learning_rate=learning_rate,
                      feature_columns=list(FEATURE_COLUMNS))

    all_features = list(range(len(FEATURE_COLUMNS)))
    n_colsample = max(1, int(round(len(all_features) * colsample)))
    best_metric, best_iteration, no_improve = -1.0, 0, 0
    history: List[Dict[str, Any]] = []
    started = time.time()

    for round_idx in range(1, n_estimators + 1):
        # ---- 一阶/二阶梯度（logistic loss + scale_pos_weight 样本权重）
        grad, hess = [0.0] * n_train, [0.0] * n_train
        for i in range(n_train):
            p = _sigmoid(margins[i])
            w = scale_pos_weight if y_train[i] == 1 else 1.0
            grad[i] = w * (p - y_train[i])
            hess[i] = max(w * p * (1.0 - p), 1e-6)

        rows = list(range(n_train))
        if subsample < 1.0:
            k = max(2, int(round(n_train * subsample)))
            rows = rng.sample(rows, k)
        features = all_features if n_colsample >= len(all_features) else rng.sample(all_features, n_colsample)

        tree = _build_tree(hist, rows, grad, hess, 0, params, features, rng)
        booster.trees.append(tree)

        for i in range(n_train):
            margins[i] += learning_rate * _walk(tree, x_train[i])
        for i in range(len(y_val)):
            val_margins[i] += learning_rate * _walk(tree, x_val[i])

        val_prob = [_sigmoid(m) for m in val_margins]
        val_auc = _auc(y_val, val_prob)
        val_logloss = -sum(
            (y_val[i] * math.log(max(val_prob[i], 1e-9))
             + (1 - y_val[i]) * math.log(max(1 - val_prob[i], 1e-9))) for i in range(len(y_val))
        ) / max(len(y_val), 1)
        monitor = val_auc if settings.XGB_EARLY_STOP_METRIC == "auc" else -val_logloss
        history.append({"round": round_idx, "val_auc": round(val_auc, 4),
                        "val_logloss": round(val_logloss, 4)})

        if monitor > best_metric + 1e-6:
            best_metric, best_iteration, no_improve = monitor, round_idx, 0
        else:
            no_improve += 1

        if round_idx % 25 == 0 or round_idx == 1:
            emit(f"  round {round_idx:>3} | val_auc={val_auc:.4f} val_logloss={val_logloss:.4f} "
                 f"best_iter={best_iteration}")

        # ---- 必做 ②早停 + 抗假收敛 ②warmup（前 N 轮强制不早停）
        if round_idx > settings.XGB_WARMUP_ROUNDS and no_improve >= settings.XGB_EARLY_STOPPING_ROUNDS:
            emit(f"早停触发: 第 {round_idx} 轮，{settings.XGB_EARLY_STOP_METRIC} "
                 f"连续 {no_improve} 轮无提升（best_iter={best_iteration}）")
            break

    booster.trees = booster.trees[:best_iteration] or booster.trees
    booster.best_iteration = best_iteration
    booster.trained_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # ---- 评估（训练集 + 验证集）
    train_prob = [booster.predict_proba(row) for row in x_train]
    val_prob = [booster.predict_proba(row) for row in x_val]
    best_threshold, best_f1 = scan_best_f1_threshold(y_val, val_prob)   # 宝典 7.8 阈值扫描
    booster.best_f1_threshold = best_threshold

    train_metrics = evaluate(y_train, train_prob, 0.5)
    val_fixed = evaluate(y_val, val_prob, 0.5)
    val_best = evaluate(y_val, val_prob, best_threshold)

    metrics.update({
        "best_iteration": best_iteration,
        "n_trees": len(booster.trees),
        "train": train_metrics,
        "val": val_fixed,
        "val_best_threshold": val_best,
        "best_f1_threshold": best_threshold,
        "best_f1": round(best_f1, 4),
        "history": history[-60:],
        "train_seconds": round(time.time() - started, 2),
        # 顶层扁平字段，方便上游程序化判断
        "acc": val_fixed["acc"], "baseline_acc": val_fixed["baseline_acc"],
        "auc": val_fixed["auc"], "ks": val_fixed["ks"],
        "precision": val_fixed["precision"], "recall": val_fixed["recall"],
        "f1": val_fixed["f1"], "val_auc": val_fixed["auc"], "val_f1": val_fixed["f1"],
    })

    # ---- 抗假收敛 ④：假收敛 3（+1）信号自动检测
    reasons: List[str] = []
    if best_iteration < settings.XGB_MIN_BEST_ITER:
        reasons.append(f"best_iteration={best_iteration} < {settings.XGB_MIN_BEST_ITER}（收敛太快=学不到东西）")
    if val_fixed["auc"] < settings.XGB_MIN_VAL_AUC:
        reasons.append(f"val_auc={val_fixed['auc']} < {settings.XGB_MIN_VAL_AUC}（整体排序能力差）")
    if max(val_fixed["f1"], best_f1) < settings.XGB_MIN_VAL_F1:
        reasons.append(f"val_f1={val_fixed['f1']} < {settings.XGB_MIN_VAL_F1}（召回不足）")
    if val_fixed["acc"] < val_fixed["baseline_acc"] + settings.XGB_BASELINE_ACC_MARGIN:
        reasons.append(f"acc={val_fixed['acc']} < baseline_acc({val_fixed['baseline_acc']}) + "
                       f"{settings.XGB_BASELINE_ACC_MARGIN}（比「全预测负例」还差）")
    metrics["is_fake_convergence"] = bool(reasons)
    metrics["fake_convergence_reasons"] = reasons

    if val_fixed["f1"] > 0 and best_f1 >= val_fixed["f1"] * 2:
        metrics["warnings"].append(
            f"固定阈值 0.5 错位：F1@0.5={val_fixed['f1']} vs F1@{best_threshold}={best_f1}，"
            f"线上建议用 best_f1_threshold")

    booster.metrics = metrics
    booster.save_model(model_path)
    emit(f"模型已保存: {model_path}")

    global _model, _native_booster, _LOADED, _LOAD_TIME, _LOAD_ERROR
    _model, _native_booster = booster, None
    _LOADED, _LOAD_ERROR = True, ""
    _LOAD_TIME = time.strftime("%Y-%m-%d %H:%M:%S")

    return (metrics, booster) if return_model else metrics


# ====================================================================== 懒加载（宝典 7.6）
def _schedule_load() -> None:
    """模块级懒加载：import 时触发，**只检查文件不阻塞**。

    settings.XGB_ENABLED = False  → 跳过，走纯规则
    xgb_model.json 不存在         → logger.warning，走纯规则
    xgb_model.json 存在           → 加载并置 _LOADED = True
    """
    global _LOAD_ERROR
    if not settings.XGB_ENABLED:
        _LOAD_ERROR = "XGB_ENABLED=False，跳过加载（纯规则模式）"
        logger.info(_LOAD_ERROR)
        return
    if not os.path.exists(settings.XGB_MODEL_PATH):
        _LOAD_ERROR = f"模型文件不存在: {settings.XGB_MODEL_PATH}（降级为纯规则，业务永不停）"
        logger.warning(_LOAD_ERROR)
        return
    load_model(settings.XGB_MODEL_PATH)


_schedule_load()
