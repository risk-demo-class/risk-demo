from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Iterable, Literal


Decision = Literal["PASS", "REVIEW", "REJECT"]


@dataclass(frozen=True, slots=True)
class ScoreResult:
    highest_rule_score: int
    hit_count: int
    raw_score: int
    model_margin: float | None
    model_probability: float | None
    model_score: int
    blended_score: int
    final_score: int
    decision: Decision


def sigmoid(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return 1 / (1 + factor)
    factor = math.exp(value)
    return factor / (1 + factor)


def round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def decision_from_score(final_score: int) -> Decision:
    if final_score >= 75:
        return "REJECT"
    if final_score >= 30:
        return "REVIEW"
    return "PASS"


def calculate_risk_score(
    rule_scores: Iterable[int], *, model_margin: float | None = None
) -> ScoreResult:
    scores = [int(score) for score in rule_scores]
    if any(score < 0 or score > 100 for score in scores):
        raise ValueError("rule scores must be between 0 and 100")

    highest_rule_score = max(scores, default=0)
    hit_count = len(scores)
    raw_score = highest_rule_score + hit_count - 1 if scores else 0
    model_probability = sigmoid(model_margin) if model_margin is not None else None
    model_score = (
        round_half_up(model_probability * 100)
        if model_probability is not None
        else 0
    )
    blended_score = round_half_up(0.6 * raw_score + 0.4 * model_score)
    final_score = min(max(raw_score, blended_score), 100)
    decision = decision_from_score(final_score)
    return ScoreResult(
        highest_rule_score=highest_rule_score,
        hit_count=hit_count,
        raw_score=raw_score,
        model_margin=model_margin,
        model_probability=model_probability,
        model_score=model_score,
        blended_score=blended_score,
        final_score=final_score,
        decision=decision,
    )


def calculate_account_age_days(
    registered_at: datetime | date,
    *,
    as_of: datetime | date | None = None,
) -> int:
    registered_date = (
        registered_at.date() if isinstance(registered_at, datetime) else registered_at
    )
    reference = as_of or date.today()
    reference_date = reference.date() if isinstance(reference, datetime) else reference
    return max((reference_date - registered_date).days, 0)
