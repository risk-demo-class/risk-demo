"""Generate an independent synthetic holdout set and evaluate all risk layers.

The evaluator works at the derived-feature layer so that rule, XGBoost, graph, and
fusion scores can be compared on exactly the same records.  Synthetic truth labels
come from noisy latent-risk functions and are never copied from platform decisions.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bootstrap import initialize_database  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import close_database, get_session_factory  # noqa: E402
from app.engine.fusion import fuse_scores  # noqa: E402
from app.engine.graph import graph_engine  # noqa: E402
from app.engine.model_manager import model_manager  # noqa: E402
from app.engine.rule import rule_engine  # noqa: E402
from app.models_risk import RiskRule  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "evaluation"
SCENARIOS = ("CARD", "LOAN", "TRANSFER", "LOGIN")
FEATURE_COLUMNS = (
    "amount",
    "event_hour",
    "transactions_1h",
    "distinct_from_cards_1h",
    "device_age_days",
    "device_user_count",
    "is_proxy",
    "is_tor",
    "beneficiary_blacklisted",
    "city_mismatch",
    "credit_score",
    "term_months",
    "monthly_income",
    "debt_ratio",
    "loan_institution_count_month",
    "login_failed",
    "graph_fraud_neighbor",
)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, value))))


def _bounded(value: float, lower: float, upper: float) -> float:
    return float(min(upper, max(lower, value)))


def _common_features(rng: np.random.Generator) -> dict[str, Any]:
    city_mismatch = bool(rng.binomial(1, 0.2))
    login_failed = bool(rng.binomial(1, 0.16))
    return {
        "amount": _bounded(float(rng.lognormal(8.5, 1.2)), 10, 250000),
        "event_hour": int(rng.integers(0, 24)),
        "transactions_1h": int(np.clip(rng.poisson(1.35) + 1, 1, 12)),
        "distinct_from_cards_1h": int(np.clip(rng.poisson(0.8) + 1, 1, 10)),
        "device_age_days": round(_bounded(float(rng.exponential(95)), 0, 730), 2),
        "device_user_count": int(np.clip(rng.poisson(0.9) + 1, 1, 15)),
        "is_proxy": bool(rng.binomial(1, 0.09)),
        "is_tor": bool(rng.binomial(1, 0.03)),
        "beneficiary_blacklisted": bool(rng.binomial(1, 0.03)),
        "city_mismatch": city_mismatch,
        "current_city": "上海" if city_mismatch else "北京",
        "usual_city": "北京",
        "credit_score": round(_bounded(float(rng.normal(645, 82)), 300, 850), 1),
        "term_months": int(rng.choice([6, 12, 24, 36, 60])),
        "monthly_income": round(_bounded(float(rng.lognormal(9.15, 0.6)), 2500, 120000), 2),
        "debt_ratio": round(_bounded(float(rng.beta(2.3, 4.3)), 0.01, 0.98), 4),
        "loan_institution_count_month": int(np.clip(rng.poisson(0.9) + 1, 1, 8)),
        "login_failed": login_failed,
        "success": not login_failed,
        "graph_fraud_neighbor": bool(rng.binomial(1, 0.08)),
        "ip": "203.0.113.25",
    }


def _latent_risk(scenario: str, f: dict[str, Any], rng: np.random.Generator) -> float:
    night = float(f["event_hour"] <= 5 or f["event_hour"] >= 23)
    new_device = float(f["device_age_days"] < 7)
    shared_device = float(f["device_user_count"] >= 5)
    graph_neighbor = float(f["graph_fraud_neighbor"])
    if scenario == "CARD":
        latent = (
            -3.9
            + f["amount"] / 33000
            + night * 1.05
            + max(f["transactions_1h"] - 2, 0) * 0.68
            + new_device * 1.15
            + shared_device * 1.45
            + float(f["is_proxy"]) * 1.25
            - (f["credit_score"] - 650) / 145
            + graph_neighbor * 1.35
            + night * float(f["transactions_1h"] >= 4) * 0.55
        )
    elif scenario == "TRANSFER":
        latent = (
            -4.35
            + f["amount"] / 28500
            + night * 0.9
            + max(f["distinct_from_cards_1h"] - 2, 0) * 1.05
            + float(f["city_mismatch"]) * 1.25
            + float(f["beneficiary_blacklisted"]) * 4.6
            + float(f["is_proxy"]) * 1.15
            + new_device * 1.05
            + graph_neighbor * 1.3
        )
    elif scenario == "LOAN":
        pressure = f["amount"] / max(f["monthly_income"] * f["term_months"], 1)
        latent = (
            -3.8
            + f["debt_ratio"] * 4.7
            + pressure * 4.2
            - (f["credit_score"] - 620) / 92
            + max(f["loan_institution_count_month"] - 1, 0) * 0.72
            + float(f["term_months"] >= 36) * 0.4
            + new_device * 0.75
            + float(f["is_proxy"]) * 0.9
            + graph_neighbor * 1.0
        )
    else:
        latent = (
            -3.75
            + night * 1.0
            + float(f["device_age_days"] < 3) * 1.35
            + max(f["device_user_count"] - 2, 0) * 0.52
            + float(f["is_proxy"]) * 1.65
            + float(f["is_tor"]) * 2.75
            + float(f["login_failed"]) * 1.15
            + graph_neighbor * 1.4
        )
    return latent + float(rng.normal(0, 0.55))


def generate_holdout(per_scenario: int, seed: int) -> list[dict[str, Any]]:
    """Build a stratified holdout with a seed distinct from model training."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for index in range(1, per_scenario + 1):
            features = _common_features(rng)
            if scenario == "CARD":
                features["beneficiary_blacklisted"] = False
                features["distinct_from_cards_1h"] = 1
            elif scenario == "LOAN":
                features["transactions_1h"] = 1
                features["distinct_from_cards_1h"] = 1
                features["beneficiary_blacklisted"] = False
            elif scenario == "LOGIN":
                features["amount"] = 0.0
                features["transactions_1h"] = 1
                features["distinct_from_cards_1h"] = 1
                features["beneficiary_blacklisted"] = False
            probability = _sigmoid(_latent_risk(scenario, features, rng))
            label = int(rng.binomial(1, probability))
            user_id = "U_SHARED_2" if features["graph_fraud_neighbor"] else "U_SAFE"
            rows.append(
                {
                    "sample_id": f"EVAL_{scenario}_{index:04d}",
                    "scenario": scenario,
                    "user_id": user_id,
                    "truth_label": label,
                    "truth_probability": round(probability, 6),
                    **features,
                }
            )
    return rows


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def calculate_metrics(rows: list[dict[str, Any]], score_field: str, threshold: int) -> dict[str, Any]:
    truth = np.asarray([int(row["truth_label"]) for row in rows], dtype=np.int32)
    scores = np.asarray([float(row[score_field]) for row in rows], dtype=np.float64)
    predicted = (scores >= threshold).astype(np.int32)
    tp = int(np.sum((truth == 1) & (predicted == 1)))
    tn = int(np.sum((truth == 0) & (predicted == 0)))
    fp = int(np.sum((truth == 0) & (predicted == 1)))
    fn = int(np.sum((truth == 1) & (predicted == 0)))
    accuracy = _safe_div(tp + tn, len(rows))
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    false_positive_rate = _safe_div(fp, fp + tn)
    false_discovery_rate = _safe_div(fp, tp + fp)
    false_negative_rate = _safe_div(fn, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    probabilities = np.clip(scores / 100.0, 0.0, 1.0)
    return {
        "samples": len(rows),
        "threshold": threshold,
        "positive_rate": round(float(truth.mean()), 6),
        "action_rate": round(float(predicted.mean()), 6),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": round(accuracy, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "specificity": round(specificity, 6),
        "false_positive_rate": round(false_positive_rate, 6),
        "false_discovery_rate": round(false_discovery_rate, 6),
        "false_negative_rate": round(false_negative_rate, 6),
        "f1": round(f1, 6),
        "balanced_accuracy": round((recall + specificity) / 2, 6),
        "roc_auc": round(float(roc_auc_score(truth, scores)), 6),
        "pr_auc": round(float(average_precision_score(truth, scores)), 6),
        "brier": round(float(brier_score_loss(truth, probabilities)), 6),
    }


async def score_holdout(rows: list[dict[str, Any]]) -> None:
    async with get_session_factory()() as session:
        rules = list(
            (
                await session.scalars(
                    select(RiskRule)
                    .where(RiskRule.is_enabled.is_(True), RiskRule.deleted_at.is_(None))
                    .order_by(RiskRule.priority.desc())
                )
            ).all()
        )
        for row in rows:
            scenario_rules = [rule for rule in rules if row["scenario"] in rule.scenarios]
            features = {key: row[key] for key in FEATURE_COLUMNS if key in row}
            features.update(
                {
                    "current_city": row["current_city"],
                    "usual_city": row["usual_city"],
                    "success": row["success"],
                    "ip": row["ip"],
                }
            )
            rule_result = rule_engine.evaluate(
                features,
                scenario_rules,
                additional_weight=settings.RULE_ADDITIONAL_WEIGHT,
            )
            model_result = model_manager.score(row["scenario"], features)
            graph_result = await graph_engine.evaluate(row["user_id"], features, session)
            model_score = model_result.score if model_result else 0
            fusion_result = fuse_scores(
                {
                    "rule": rule_result.score,
                    "model": model_score,
                    "graph": graph_result.score,
                },
                additional_weight=settings.FUSION_ADDITIONAL_WEIGHT,
                minimum_decision=rule_result.decision,
                minimum_level=rule_result.risk_level,
            )
            row.update(
                {
                    "rule_score": rule_result.score,
                    "model_score": model_score,
                    "graph_score": graph_result.score,
                    "final_score": fusion_result.score,
                    "risk_level": fusion_result.risk_level,
                    "decision": fusion_result.decision,
                    "hit_rules": ",".join(hit.rule_id for hit in rule_result.hits),
                    "model_version": model_result.version if model_result else "",
                    "graph_signals": ",".join(graph_result.signals),
                    "predicted_risk": int(fusion_result.score >= 30),
                }
            )
            truth = int(row["truth_label"])
            prediction = int(row["predicted_risk"])
            row["error_type"] = (
                "TP"
                if truth == 1 and prediction == 1
                else "TN"
                if truth == 0 and prediction == 0
                else "FP"
                if truth == 0
                else "FN"
            )


def build_summary(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    layers = {
        "RULE": calculate_metrics(rows, "rule_score", 30),
        "MODEL": calculate_metrics(rows, "model_score", 30),
        "GRAPH": calculate_metrics(rows, "graph_score", 30),
        "FUSION": calculate_metrics(rows, "final_score", 30),
    }
    scenarios = {
        scenario: calculate_metrics(
            [row for row in rows if row["scenario"] == scenario],
            "final_score",
            30,
        )
        for scenario in SCENARIOS
    }
    thresholds = {
        str(threshold): calculate_metrics(rows, "final_score", threshold)
        for threshold in (30, 50, 80)
    }
    level_distribution = dict(Counter(str(row["risk_level"]) for row in rows))
    decision_distribution = dict(Counter(str(row["decision"]) for row in rows))
    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "seed": seed,
            "dataset_type": "independent_synthetic_feature_holdout",
            "samples": len(rows),
            "samples_per_scenario": len(rows) // len(SCENARIOS),
            "primary_threshold": 30,
            "positive_definition": "truth_label=1 means fraud/default/account-takeover risk",
            "predicted_positive_definition": "final_score >= 30 (FLAG/REVIEW/REJECT)",
            "false_positive_rate_definition": "FP/(FP+TN), normal samples incorrectly actioned",
            "false_negative_rate_definition": "FN/(TP+FN), risky samples incorrectly passed",
            "limitation": "Synthetic feature-level evaluation; not a substitute for governed out-of-time bank labels.",
        },
        "layers_at_threshold_30": layers,
        "fusion_by_scenario_at_threshold_30": scenarios,
        "fusion_threshold_sensitivity": thresholds,
        "risk_level_distribution": level_distribution,
        "decision_distribution": decision_distribution,
    }


def write_artifacts(rows: list[dict[str, Any]], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_path = output_dir / "risk_evaluation_details.csv"
    summary_path = output_dir / "risk_evaluation_summary.json"
    columns = (
        "sample_id",
        "scenario",
        "user_id",
        "truth_label",
        "truth_probability",
        *FEATURE_COLUMNS,
        "rule_score",
        "model_score",
        "graph_score",
        "final_score",
        "risk_level",
        "decision",
        "predicted_risk",
        "error_type",
        "hit_rules",
        "graph_signals",
        "model_version",
    )
    with detail_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


async def async_main(per_scenario: int, seed: int, output_dir: Path) -> int:
    original_driver = settings.DB_DRIVER
    original_path = settings.SQLITE_PATH
    original_graph_backend = settings.GRAPH_BACKEND
    temporary = tempfile.TemporaryDirectory(prefix="bankrisk-metric-eval-")
    settings.DB_DRIVER = "sqlite"
    settings.SQLITE_PATH = str(Path(temporary.name) / "evaluation.db")
    settings.GRAPH_BACKEND = "local"
    try:
        await close_database()
        await initialize_database(seed_demo=True)
        if not model_manager.ensure_ready():
            raise RuntimeError("Model registry is not ready")
        rows = generate_holdout(per_scenario=per_scenario, seed=seed)
        await score_holdout(rows)
        summary = build_summary(rows, seed=seed)
        write_artifacts(rows, summary, output_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        await close_database()
        settings.DB_DRIVER = original_driver
        settings.SQLITE_PATH = original_path
        settings.GRAPH_BACKEND = original_graph_backend
        temporary.cleanup()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-scenario", type=int, default=500, choices=range(100, 5001))
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(async_main(args.per_scenario, args.seed, args.output_dir)))
