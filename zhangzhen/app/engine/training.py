"""XGBoost 训练集提取、纯度校验、时间切分和模型训练。"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.feature import FEATURE_COLUMNS
from app.models import Decision
from app.models_risk import RiskAssessment, RiskEvent, RiskFeature


logger = logging.getLogger(__name__)
POSITIVE_DECISIONS = {Decision.MANUAL_REVIEW, Decision.REJECT}


@dataclass(frozen=True, slots=True)
class TrainingSample:
    assessment_id: str
    event_id: str
    user_id: str
    event_time: datetime
    features: tuple[float, ...]
    label: int


@dataclass(frozen=True, slots=True)
class DatasetValidation:
    samples: int
    positives: int
    negatives: int
    positive_ratio: float
    feature_count: int
    start_time: str
    end_time: str
    span_days: int


@dataclass(frozen=True, slots=True)
class TrainingMetrics:
    train_samples: int
    validation_samples: int
    train_positive_ratio: float
    validation_positive_ratio: float
    validation_auc: float
    validation_f1: float
    validation_precision: float
    validation_recall: float
    threshold: float
    best_iteration: int
    feature_count: int
    split_method: str
    model_path: str


async def load_training_samples(
    db: AsyncSession,
    *,
    limit: int | None = None,
) -> list[TrainingSample]:
    """只读取模型尚未参与过的评估，避免模型输出反过来污染标签。"""

    statement = (
        select(RiskAssessment, RiskEvent)
        .join(RiskEvent, RiskEvent.event_id == RiskAssessment.event_id)
        .where(RiskAssessment.ml_score.is_(None))
        .order_by(RiskAssessment.create_time.asc(), RiskAssessment.assessment_id.asc())
    )
    if limit is not None and limit > 0:
        statement = statement.limit(limit)
    assessment_rows = (await db.execute(statement)).all()
    if not assessment_rows:
        return []

    event_ids = [assessment.event_id for assessment, _ in assessment_rows]
    feature_rows = (
        await db.execute(
            select(RiskFeature.event_id, RiskFeature.feature_name, RiskFeature.feature_value)
            .where(RiskFeature.event_id.in_(event_ids))
            .order_by(RiskFeature.event_id, RiskFeature.feature_id)
        )
    ).all()
    by_event: dict[str, dict[str, float]] = {}
    for event_id, feature_name, feature_value in feature_rows:
        by_event.setdefault(event_id, {})[feature_name] = float(feature_value)

    samples: list[TrainingSample] = []
    for assessment, event in assessment_rows:
        values = by_event.get(assessment.event_id, {})
        # 任何缺维或多维样本都拒绝进入训练，而不是静默补 0。
        if set(values) != set(FEATURE_COLUMNS):
            logger.warning(
                "跳过特征不完整样本 assessment_id=%s expected=%d actual=%d",
                assessment.assessment_id,
                len(FEATURE_COLUMNS),
                len(values),
            )
            continue
        samples.append(
            TrainingSample(
                assessment_id=assessment.assessment_id,
                event_id=assessment.event_id,
                user_id=assessment.user_id,
                event_time=assessment.create_time,
                features=tuple(values[name] for name in FEATURE_COLUMNS),
                label=int(assessment.decision in POSITIVE_DECISIONS),
            )
        )
    return samples


def validate_training_samples(
    samples: list[TrainingSample],
    *,
    min_samples: int = 1250,
    min_positive_ratio: float = 0.15,
    max_positive_ratio: float = 0.60,
    min_span_days: int = 30,
) -> DatasetValidation:
    if len(FEATURE_COLUMNS) != 25:
        raise ValueError(f"特征契约必须严格等于 25 维，当前为 {len(FEATURE_COLUMNS)}")
    if len(samples) < min_samples:
        raise ValueError(f"训练样本不足：{len(samples)} < {min_samples}")
    if any(len(sample.features) != len(FEATURE_COLUMNS) for sample in samples):
        raise ValueError("存在非 25 维训练样本")
    positives = sum(sample.label for sample in samples)
    negatives = len(samples) - positives
    ratio = positives / len(samples)
    if not min_positive_ratio <= ratio <= max_positive_ratio:
        raise ValueError(
            f"正例比例 {ratio:.2%} 不在 {min_positive_ratio:.0%}~{max_positive_ratio:.0%} 范围"
        )
    times = [sample.event_time for sample in samples]
    span_days = (max(times) - min(times)).days
    if span_days < min_span_days:
        raise ValueError(f"训练数据日期跨度不足：{span_days} 天 < {min_span_days} 天")
    return DatasetValidation(
        samples=len(samples), positives=positives, negatives=negatives,
        positive_ratio=ratio, feature_count=len(FEATURE_COLUMNS),
        start_time=min(times).isoformat(), end_time=max(times).isoformat(), span_days=span_days,
    )


def export_training_csv(path: Path, samples: list[TrainingSample]) -> None:
    """CSV 最后一列是标签；训练函数只把固定 25 列作为 X。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["assessment_id", "event_id", "user_id", "event_time", *FEATURE_COLUMNS, "label"]
        )
        for sample in samples:
            writer.writerow(
                [sample.assessment_id, sample.event_id, sample.user_id,
                 sample.event_time.isoformat(), *sample.features, sample.label]
            )


def _time_split(
    samples: list[TrainingSample],
    *,
    validation_ratio: float,
) -> tuple[list[TrainingSample], list[TrainingSample], str]:
    ordered = sorted(samples, key=lambda item: (item.event_time, item.assessment_id))
    split_at = min(max(int(len(ordered) * (1 - validation_ratio)), 1), len(ordered) - 1)
    train = ordered[:split_at]
    validation = ordered[split_at:]

    # 优先净化同用户泄漏；若净化会使训练集失去任一类别，则保留纯时间切分并明确记录。
    validation_users = {sample.user_id for sample in validation}
    purged = [sample for sample in train if sample.user_id not in validation_users]
    if len(purged) >= max(20, int(len(train) * 0.25)) and {s.label for s in purged} == {0, 1}:
        return purged, validation, "time_split_with_user_purge"
    return train, validation, "time_split"


def _best_threshold(labels, probabilities) -> tuple[float, float]:
    from sklearn.metrics import f1_score

    best_threshold = 0.5
    best_f1 = -1.0
    for raw in range(20, 81, 2):
        threshold = raw / 100
        predictions = (probabilities >= threshold).astype(int)
        score = float(f1_score(labels, predictions, zero_division=0))
        if score > best_f1:
            best_threshold, best_f1 = threshold, score
    return best_threshold, best_f1


def train_xgboost_model(
    samples: list[TrainingSample],
    *,
    model_path: Path,
    validation_ratio: float = 0.20,
    rounds: int = 300,
    early_stopping_rounds: int = 25,
    seed: int = 20260813,
) -> TrainingMetrics:
    """按时间切分训练，并保存与线上 Booster 加载器兼容的 JSON 模型。"""

    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import precision_score, recall_score, roc_auc_score

    train, validation, split_method = _time_split(samples, validation_ratio=validation_ratio)
    if {sample.label for sample in train} != {0, 1}:
        raise ValueError("训练集必须同时包含正例和负例")
    if {sample.label for sample in validation} != {0, 1}:
        raise ValueError("验证集必须同时包含正例和负例，请增加日期跨度或样本量")

    train_x = np.asarray([sample.features for sample in train], dtype=np.float32)
    train_y = np.asarray([sample.label for sample in train], dtype=np.int32)
    val_x = np.asarray([sample.features for sample in validation], dtype=np.float32)
    val_y = np.asarray([sample.label for sample in validation], dtype=np.int32)
    train_matrix = xgb.DMatrix(train_x, label=train_y, feature_names=list(FEATURE_COLUMNS))
    val_matrix = xgb.DMatrix(val_x, label=val_y, feature_names=list(FEATURE_COLUMNS))
    positives = int(train_y.sum())
    negatives = len(train_y) - positives
    scale_pos_weight = min(max(negatives / max(positives, 1), 1.0), 5.0)

    booster = xgb.train(
        {
            "objective": "binary:logistic", "eval_metric": ["auc", "logloss"],
            "max_depth": 5, "eta": 0.06, "min_child_weight": 3,
            "subsample": 0.85, "colsample_bytree": 0.85,
            "reg_alpha": 0.1, "reg_lambda": 1.5,
            "scale_pos_weight": scale_pos_weight, "seed": seed,
        },
        train_matrix,
        num_boost_round=rounds,
        evals=[(train_matrix, "train"), (val_matrix, "validation")],
        early_stopping_rounds=early_stopping_rounds,
        verbose_eval=False,
    )
    probabilities = booster.predict(val_matrix)
    threshold, f1 = _best_threshold(val_y, probabilities)
    predictions = (probabilities >= threshold).astype(int)
    auc = float(roc_auc_score(val_y, probabilities))
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.set_attr(
        bank_risk_feature_count=str(len(FEATURE_COLUMNS)),
        bank_risk_feature_names=json.dumps(FEATURE_COLUMNS, ensure_ascii=False),
        classification_threshold=str(threshold),
    )
    booster.save_model(model_path)
    metrics = TrainingMetrics(
        train_samples=len(train), validation_samples=len(validation),
        train_positive_ratio=float(train_y.mean()),
        validation_positive_ratio=float(val_y.mean()), validation_auc=auc,
        validation_f1=f1,
        validation_precision=float(precision_score(val_y, predictions, zero_division=0)),
        validation_recall=float(recall_score(val_y, predictions, zero_division=0)),
        threshold=threshold, best_iteration=int(booster.best_iteration),
        feature_count=len(FEATURE_COLUMNS), split_method=split_method,
        model_path=str(model_path),
    )
    metrics_path = model_path.with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(asdict(metrics), ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics
