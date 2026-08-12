"""Fusion policy for rule, calibrated model and graph scores."""

from dataclasses import dataclass
from math import floor

from app.engine.rule import score_outcome


_DECISION_WEIGHT = {"通过": 0, "标记": 1, "人工审核": 2, "拒绝": 3}
_LEVEL_WEIGHT = {"低": 0, "中": 1, "高": 2, "极高": 3}
_DECISION_LEVEL = {"通过": "低", "标记": "中", "人工审核": "高", "拒绝": "极高"}


@dataclass(frozen=True, slots=True)
class FusionEvaluation:
    score: int
    risk_level: str
    decision: str
    primary_component: str
    primary_score: int
    other_components_score_sum: int
    additional_weight: float
    weighted_addition: float
    raw_score: float
    component_scores: dict[str, int]


def fuse_scores(
    component_scores: dict[str, int],
    additional_weight: float = 0.15,
    minimum_decision: str = "通过",
    minimum_level: str = "低",
) -> FusionEvaluation:
    if not 0 <= additional_weight <= 1:
        raise ValueError("additional_weight must be between 0 and 1")
    normalized = {name: min(100, max(0, int(score))) for name, score in component_scores.items()}
    if not normalized:
        normalized = {"none": 0}
    ordered = sorted(normalized.items(), key=lambda item: (item[1], item[0]), reverse=True)
    primary_component, primary_score = ordered[0]
    other_sum = sum(score for _, score in ordered[1:])
    weighted_addition = other_sum * additional_weight
    raw_score = primary_score + weighted_addition
    final_score = min(100, floor(raw_score + 0.5))
    score_level, score_decision = score_outcome(final_score)
    final_decision = max(
        (score_decision, minimum_decision),
        key=lambda decision: _DECISION_WEIGHT[decision],
    )
    final_level = max(
        (score_level, minimum_level, _DECISION_LEVEL[final_decision]),
        key=lambda level: _LEVEL_WEIGHT[level],
    )
    return FusionEvaluation(
        score=final_score,
        risk_level=final_level,
        decision=final_decision,
        primary_component=primary_component,
        primary_score=primary_score,
        other_components_score_sum=other_sum,
        additional_weight=additional_weight,
        weighted_addition=round(weighted_addition, 4),
        raw_score=round(raw_score, 4),
        component_scores=normalized,
    )
