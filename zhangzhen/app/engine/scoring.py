"""规则分、模型分、一票否决和四档风险输出。"""

from dataclasses import dataclass
from math import exp

from app.models import Decision, RiskLevel
from app.schemas import TriggeredRule


@dataclass(frozen=True, slots=True)
class DecisionResult:
    rule_score: int
    final_score: int
    risk_level: RiskLevel
    decision: Decision
    ml_probability: float | None
    ml_decision: Decision | None
    vetoed: bool


def calculate_rule_score(triggered_rules: list[TriggeredRule]) -> int:
    if not triggered_rules:
        return 0
    highest = max(rule.risk_score for rule in triggered_rules)
    extra_hits = len(triggered_rules) - 1
    return min(highest + 3 * extra_hits, 100)


def score_to_outcome(score: int) -> tuple[RiskLevel, Decision]:
    if score <= 29:
        return RiskLevel.LOW, Decision.PASS
    if score <= 59:
        return RiskLevel.MEDIUM, Decision.FLAG
    if score <= 84:
        return RiskLevel.HIGH, Decision.MANUAL_REVIEW
    return RiskLevel.EXTREME, Decision.REJECT


def ml_probability_to_risk_score(probability: float) -> int:
    return min(max(round(100 * (1 - exp(-3 * probability))), 0), 100)


def make_decision(
    triggered_rules: list[TriggeredRule],
    ml_probability: float | None,
    *,
    rule_weight: float = 0.5,
    ml_weight: float = 0.5,
) -> DecisionResult:
    rule_score = calculate_rule_score(triggered_rules)
    vetoed = any(rule.risk_level is RiskLevel.EXTREME for rule in triggered_rules)

    ml_decision: Decision | None = None
    if ml_probability is None:
        final_score = rule_score
    else:
        ml_risk_score = ml_probability_to_risk_score(ml_probability)
        _, ml_decision = score_to_outcome(ml_risk_score)
        final_score = round(rule_weight * rule_score + ml_weight * ml_risk_score)
        final_score = min(max(final_score, 0), 100)

    if vetoed:
        final_score = max(final_score, 90)
        return DecisionResult(
            rule_score=rule_score,
            final_score=final_score,
            risk_level=RiskLevel.EXTREME,
            decision=Decision.REJECT,
            ml_probability=ml_probability,
            ml_decision=ml_decision,
            vetoed=True,
        )

    risk_level, decision = score_to_outcome(final_score)
    return DecisionResult(
        rule_score=rule_score,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_probability=ml_probability,
        ml_decision=ml_decision,
        vetoed=False,
    )

