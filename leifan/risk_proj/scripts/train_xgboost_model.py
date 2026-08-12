from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import xgboost as xgb
from sqlalchemy import select

from app.database import SessionLocal
from app.ml_model import FEATURE_NAMES, load_feature_context, resolve_model_path
from app.models import OrderInfo, ReviewCase, RiskAssessment, UserInfo


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the OTA travel-risk XGBoost binary classifier"
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="output model path; defaults to models/travel_risk_xgboost.ubj",
    )
    parser.add_argument("--rounds", type=int, default=240)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument(
        "--manual-only",
        action="store_true",
        help="only use completed manual review outcomes as labels",
    )
    args = parser.parse_args()
    if args.rounds < 10:
        parser.error("--rounds must be at least 10")
    if not 0.1 <= args.validation_ratio <= 0.4:
        parser.error("--validation-ratio must be between 0.1 and 0.4")
    return args


def sigmoid_array(margins: np.ndarray) -> np.ndarray:
    clipped = np.clip(margins, -40, 40)
    return 1.0 / (1.0 + np.exp(-clipped))


def stratified_split(
    labels: np.ndarray, validation_ratio: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    train_indices: list[int] = []
    validation_indices: list[int] = []
    for label in (0, 1):
        indices = np.flatnonzero(labels == label)
        rng.shuffle(indices)
        if len(indices) < 2:
            raise RuntimeError(f"label {label} needs at least two samples")
        validation_count = min(
            max(1, round(len(indices) * validation_ratio)), len(indices) - 1
        )
        validation_indices.extend(indices[:validation_count].tolist())
        train_indices.extend(indices[validation_count:].tolist())
    rng.shuffle(train_indices)
    rng.shuffle(validation_indices)
    return np.asarray(train_indices), np.asarray(validation_indices)


def binary_auc(labels: np.ndarray, probabilities: np.ndarray) -> float:
    positive = probabilities[labels == 1]
    negative = probabilities[labels == 0]
    comparisons = sum(
        float(value > other) + 0.5 * float(value == other)
        for value in positive
        for other in negative
    )
    return comparisons / (len(positive) * len(negative))


def main() -> None:
    args = parse_arguments()
    trained_at = datetime.now()
    model_path = resolve_model_path(args.model_path)

    with SessionLocal() as session:
        orders = list(
            session.scalars(
                select(OrderInfo).order_by(OrderInfo.order_time, OrderInfo.order_id)
            )
        )
        users = {item.user_id: item for item in session.scalars(select(UserInfo))}
        assessments = {
            item.order_id: item for item in session.scalars(select(RiskAssessment))
        }
        review_cases = {
            item.assessment_id: item for item in session.scalars(select(ReviewCase))
        }
        context = load_feature_context(session, as_of=trained_at)

        vectors: list[list[float]] = []
        labels: list[int] = []
        label_sources: list[str] = []
        for order in orders:
            assessment = assessments.get(order.order_id)
            if assessment is None:
                continue
            review_case = review_cases.get(assessment.assessment_id)
            if review_case is not None and review_case.status in {"APPROVED", "REJECTED"}:
                label = int(review_case.status == "REJECTED")
                source = "manual_review"
            elif not args.manual_only and assessment.decision in {"PASS", "REJECT"}:
                label = int(assessment.decision == "REJECT")
                source = "weak_assessment"
            else:
                continue
            vectors.append(context.vector(order, users[order.user_id]))
            labels.append(label)
            label_sources.append(source)

    if len(labels) < 40:
        raise RuntimeError(
            f"Only {len(labels)} labeled rows are available; at least 40 are required"
        )
    label_counts = Counter(labels)
    if set(label_counts) != {0, 1}:
        raise RuntimeError("Training data must contain both safe and risky labels")

    features = np.asarray(vectors, dtype=np.float32)
    target = np.asarray(labels, dtype=np.int32)
    train_indices, validation_indices = stratified_split(
        target, args.validation_ratio, args.seed
    )
    train_matrix = xgb.DMatrix(
        features[train_indices],
        label=target[train_indices],
        feature_names=list(FEATURE_NAMES),
    )
    validation_matrix = xgb.DMatrix(
        features[validation_indices],
        label=target[validation_indices],
        feature_names=list(FEATURE_NAMES),
    )
    train_labels = target[train_indices]
    positive_count = max(int(np.sum(train_labels == 1)), 1)
    negative_count = max(int(np.sum(train_labels == 0)), 1)

    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": 4,
        "eta": 0.06,
        "min_child_weight": 2,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "lambda": 1.0,
        "alpha": 0.1,
        "scale_pos_weight": negative_count / positive_count,
        "seed": args.seed,
        "nthread": 2,
    }
    booster = xgb.train(
        params,
        train_matrix,
        num_boost_round=args.rounds,
        evals=[(train_matrix, "train"), (validation_matrix, "validation")],
        early_stopping_rounds=25,
        verbose_eval=False,
    )

    validation_margin = booster.predict(validation_matrix, output_margin=True)
    validation_probability = sigmoid_array(validation_margin)
    validation_labels = target[validation_indices]
    predictions = (validation_probability >= 0.5).astype(np.int32)
    accuracy = float(np.mean(predictions == validation_labels))
    auc = binary_auc(validation_labels, validation_probability)
    clipped_probability = np.clip(validation_probability, 1e-7, 1 - 1e-7)
    logloss = -float(
        np.mean(
            validation_labels * np.log(clipped_probability)
            + (1 - validation_labels) * np.log(1 - clipped_probability)
        )
    )

    version = f"xgb-{trained_at:%Y%m%d%H%M%S}"
    booster.set_attr(
        model_version=version,
        feature_schema_version="1",
        score_mapping="sigmoid(raw_margin)*100",
        score_fusion="min(max(rule_score,round(0.6*rule_score+0.4*model_score)),100)",
    )
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(model_path)

    metadata = {
        "model_version": version,
        "trained_at": trained_at.isoformat(),
        "model_path": str(model_path),
        "feature_names": list(FEATURE_NAMES),
        "training_rows": len(labels),
        "training_label_counts": {
            "safe": int(label_counts[0]),
            "risky": int(label_counts[1]),
        },
        "label_sources": dict(Counter(label_sources)),
        "validation_rows": int(len(validation_indices)),
        "validation_accuracy": round(accuracy, 6),
        "validation_auc": round(auc, 6),
        "validation_logloss": round(logloss, 6),
        "best_iteration": int(booster.best_iteration),
        "parameters": params,
        "score_mapping": "p=sigmoid(z); model_score=round(p*100)",
        "score_fusion": "final=min(max(rule_score,round(0.6*rule_score+0.4*model_score)),100)",
        "weak_supervision_warning": bool(
            Counter(label_sources).get("weak_assessment", 0)
        ),
    }
    metadata_path = model_path.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Model saved to {model_path}")
    print(f"Metadata saved to {metadata_path}")
    print(
        f"Rows={len(labels)}, validation AUC={auc:.4f}, "
        f"accuracy={accuracy:.4f}, logloss={logloss:.4f}"
    )
    if metadata["weak_supervision_warning"]:
        print(
            "Warning: weak assessment labels were used. Retrain with verified manual "
            "outcomes before production use."
        )


if __name__ == "__main__":
    main()
