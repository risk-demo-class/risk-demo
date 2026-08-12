"""医疗风险 XGBoost 模型加载、校准推理与安全降级。"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
import xgboost as xgb

from app.config import settings
from app.engine.feature import FEATURE_COLUMNS


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MlResult:
    score: float | None
    decision: str | None
    is_loaded: bool
    error: str | None = None


_MODEL: xgb.Booster | None = None
_METADATA: dict[str, Any] = {}
_LOCK = RLock()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def load_model() -> bool:
    """加载模型和元数据；任何异常都只关闭 ML 分支，不阻断服务。"""
    global _MODEL, _METADATA
    with _LOCK:
        _MODEL, _METADATA = None, {}
        if not settings.XGB_ENABLED:
            return False
        model_path = _resolve(settings.XGB_MODEL_PATH)
        metadata_path = _resolve(settings.XGB_METADATA_PATH)
        if not model_path.exists() or not metadata_path.exists():
            return False
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("feature_columns") != FEATURE_COLUMNS:
                raise ValueError("模型特征列或顺序与当前 25 维特征不一致")
            model = xgb.Booster()
            model.load_model(model_path)
            _MODEL, _METADATA = model, metadata
            logger.info("XGBoost 医疗风控模型已加载: %s", model_path)
            return True
        except Exception as exc:  # 模型损坏不能影响规则主链路
            logger.warning("XGBoost 模型加载失败，已降级为纯规则: %s", exc)
            return False


def is_model_loaded() -> bool:
    return _MODEL is not None


def model_status() -> dict[str, Any]:
    return {
        "enabled": settings.XGB_ENABLED,
        "loaded": is_model_loaded(),
        "model_path": settings.XGB_MODEL_PATH,
        "trained_at": _METADATA.get("trained_at"),
        "validation_auc": _METADATA.get("metrics", {}).get("validation_auc"),
        "validation_f1": _METADATA.get("metrics", {}).get("validation_f1"),
        "label_strategy": _METADATA.get("label_strategy"),
    }


def features_to_matrix(features: dict[str, Any]) -> np.ndarray:
    row: list[float] = []
    for column in FEATURE_COLUMNS:
        try:
            value = float(features.get(column, 0.0) or 0.0)
            row.append(value if math.isfinite(value) else 0.0)
        except (TypeError, ValueError):
            row.append(0.0)
    return np.asarray([row], dtype=np.float32)


def _decision_thresholds() -> tuple[float, float, float]:
    values = _METADATA.get("decision_thresholds") or {}
    return (
        float(values.get("pass", settings.ML_PASS_THRESHOLD)),
        float(values.get("mark", settings.ML_MARK_THRESHOLD)),
        float(values.get("review", settings.ML_REVIEW_THRESHOLD)),
    )


def probability_to_decision(probability: float) -> str:
    pass_threshold, mark_threshold, review_threshold = _decision_thresholds()
    if probability < pass_threshold:
        return "通过"
    if probability < mark_threshold:
        return "标记"
    if probability < review_threshold:
        return "人工审核"
    return "拒绝"


def predict(features: dict[str, Any]) -> MlResult:
    """返回校准后的高风险概率；不可用时以 None 表示纯规则降级。"""
    if _MODEL is None:
        return MlResult(None, None, False, "模型未加载")
    try:
        matrix = xgb.DMatrix(features_to_matrix(features), feature_names=FEATURE_COLUMNS)
        best_iteration = int(_METADATA.get("best_iteration", -1))
        kwargs = {"iteration_range": (0, best_iteration + 1)} if best_iteration >= 0 else {}
        margin = float(_MODEL.predict(matrix, output_margin=True, **kwargs)[0])
        calibration = _METADATA.get("platt_calibration") or {"coefficient": 1.0, "intercept": 0.0}
        probability = _sigmoid(
            float(calibration.get("coefficient", 1.0)) * margin
            + float(calibration.get("intercept", 0.0))
        )
        probability = round(min(max(probability, 0.0), 1.0), 4)
        return MlResult(probability, probability_to_decision(probability), True)
    except Exception as exc:
        logger.exception("XGBoost 推理失败，当前请求降级为纯规则")
        return MlResult(None, None, False, str(exc))


load_model()
