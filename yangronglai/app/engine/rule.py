"""Deterministic, data-driven bank rule engine."""

from dataclasses import dataclass
from math import floor
from typing import Any, Protocol


class RuleLike(Protocol):
    rule_id: str
    rule_name: str
    condition: dict[str, Any]
    risk_level: str
    risk_score: int
    decision: str
    priority: int
    version: str


@dataclass(frozen=True, slots=True)
class RuleHitResult:
    rule_id: str
    rule_name: str
    risk_score: int
    risk_level: str
    decision: str
    priority: int
    version: str
    condition: dict[str, Any]
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    score: int
    risk_level: str
    decision: str
    hits: tuple[RuleHitResult, ...]
    highest_rule_score: int = 0
    other_rules_score_sum: int = 0
    additional_weight: float = 0.0
    weighted_addition: float = 0.0
    raw_score: float = 0.0


_DECISION_WEIGHT = {"通过": 0, "标记": 1, "人工审核": 2, "拒绝": 3}
_RISK_LEVEL_WEIGHT = {"低": 0, "中": 1, "高": 2, "极高": 3}
_DECISION_RISK_LEVEL = {"通过": "低", "标记": "中", "人工审核": "高", "拒绝": "极高"}


def score_outcome(score: int) -> tuple[str, str]:
    """Map the aggregate score to the platform's four fixed bands."""
    if score >= 80:
        return "极高", "拒绝"
    if score >= 50:
        return "高", "人工审核"
    if score >= 30:
        return "中", "标记"
    return "低", "通过"


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if actual is None or expected is None:
        return False
    try:
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == ">":
            return actual > expected
        if operator == ">=":
            return actual >= expected
        if operator == "<":
            return actual < expected
        if operator == "<=":
            return actual <= expected
        if operator == "between":
            return expected[0] <= actual <= expected[1]
        if operator == "in":
            return actual in expected
    except (TypeError, ValueError, IndexError):
        return False
    raise ValueError(f"unsupported rule operator: {operator}")


def evaluate_condition(condition: dict[str, Any], features: dict[str, Any]) -> bool:
    """Evaluate a small allow-listed expression language; no ``eval`` is used."""
    if "and" in condition:
        return all(evaluate_condition(item, features) for item in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(item, features) for item in condition["or"])
    field = condition["field"]
    expected = (
        features.get(condition["value_field"])
        if "value_field" in condition
        else condition.get("value")
    )
    return _compare(features.get(field), condition["op"], expected)


def condition_evidence(condition: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    """Return only fields referenced by the condition for explainable audit."""
    evidence: dict[str, Any] = {}
    if "and" in condition or "or" in condition:
        branch = condition.get("and", condition.get("or", []))
        for item in branch:
            evidence.update(condition_evidence(item, features))
        return evidence
    evidence[condition["field"]] = features.get(condition["field"])
    if "value_field" in condition:
        evidence[condition["value_field"]] = features.get(condition["value_field"])
    return evidence


class RuleEngine:
    name = "bank-rule-engine"
    ready = True
    version = "bank-rule-v1"

    def evaluate(
        self,
        features: dict[str, Any],
        rules: list[RuleLike],
        additional_weight: float = 0.2,
    ) -> RuleEvaluation:
        if not 0 <= additional_weight <= 1:
            raise ValueError("additional_weight must be between 0 and 1")
        hits = [
            RuleHitResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                risk_score=rule.risk_score,
                risk_level=rule.risk_level,
                decision=rule.decision,
                priority=rule.priority,
                version=rule.version,
                condition=rule.condition,
                evidence=condition_evidence(rule.condition, features),
            )
            for rule in rules
            if evaluate_condition(rule.condition, features)
        ]
        hits.sort(key=lambda item: (item.priority, item.risk_score), reverse=True)
        if not hits:
            return RuleEvaluation(
                score=0,
                risk_level="低",
                decision="通过",
                hits=(),
                additional_weight=additional_weight,
            )

        strongest_rule = max(
            hits,
            key=lambda item: (_DECISION_WEIGHT[item.decision], item.risk_score, item.priority),
        )
        ordered_scores = sorted((item.risk_score for item in hits), reverse=True)
        highest_rule_score = ordered_scores[0]
        other_rules_score_sum = sum(ordered_scores[1:])
        weighted_addition = other_rules_score_sum * additional_weight
        raw_score = highest_rule_score + weighted_addition
        aggregate_score = min(100, floor(raw_score + 0.5))
        score_level, score_decision = score_outcome(aggregate_score)
        final_decision = max(
            (score_decision, strongest_rule.decision),
            key=lambda decision: _DECISION_WEIGHT[decision],
        )
        candidate_levels = [
            score_level,
            strongest_rule.risk_level,
            _DECISION_RISK_LEVEL[final_decision],
        ]
        final_level = max(candidate_levels, key=lambda level: _RISK_LEVEL_WEIGHT[level])
        return RuleEvaluation(
            score=aggregate_score,
            risk_level=final_level,
            decision=final_decision,
            hits=tuple(hits),
            highest_rule_score=highest_rule_score,
            other_rules_score_sum=other_rules_score_sum,
            additional_weight=additional_weight,
            weighted_addition=round(weighted_addition, 4),
            raw_score=round(raw_score, 4),
        )


rule_engine = RuleEngine()
