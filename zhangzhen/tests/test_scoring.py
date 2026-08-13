from app.engine.scoring import calculate_rule_score, make_decision, ml_probability_to_risk_score
from app.models import Decision, RiskLevel
from app.schemas import TriggeredRule


def _rule(rule_id: str, score: int, level: RiskLevel) -> TriggeredRule:
    return TriggeredRule(
        rule_id=rule_id,
        rule_name=rule_id,
        risk_level=level,
        risk_score=score,
        action=Decision.REJECT if level is RiskLevel.EXTREME else Decision.MANUAL_REVIEW,
        condition={"field": "x", "op": ">", "value": 1},
        actual_values={"x": 2},
    )


def test_rule_score_uses_max_plus_three_for_each_extra_hit() -> None:
    rules = [_rule("A", 70, RiskLevel.HIGH), _rule("B", 60, RiskLevel.HIGH)]

    assert calculate_rule_score(rules) == 73


def test_missing_model_uses_pure_rule_score() -> None:
    result = make_decision([_rule("A", 70, RiskLevel.HIGH)], None)

    assert result.rule_score == 70
    assert result.ml_risk_score is None
    assert result.rule_weight == 1.0
    assert result.ml_weight == 0.0
    assert result.fusion_score == 70
    assert result.final_score == 70
    assert result.decision is Decision.MANUAL_REVIEW
    assert result.ml_decision is None


def test_extreme_rule_veto_cannot_be_lowered_by_model() -> None:
    result = make_decision([_rule("A", 90, RiskLevel.EXTREME)], 0.01)

    assert result.final_score >= 90
    assert result.risk_level is RiskLevel.EXTREME
    assert result.decision is Decision.REJECT
    assert result.vetoed


def test_score_breakdown_matches_the_actual_fusion_formula() -> None:
    rules = [
        _rule("A", 90, RiskLevel.EXTREME),
        _rule("B", 75, RiskLevel.HIGH),
        _rule("C", 70, RiskLevel.HIGH),
        _rule("D", 50, RiskLevel.MEDIUM),
    ]
    result = make_decision(rules, 0.9765215516090393)

    assert result.rule_score == 99
    assert result.ml_risk_score == 95
    assert result.rule_weight == 0.5
    assert result.ml_weight == 0.5
    assert result.fusion_score == 97
    assert result.final_score == 97
    assert result.vetoed is True


def test_ml_sigmoid_like_mapping_is_bounded() -> None:
    assert ml_probability_to_risk_score(0) == 0
    assert 0 < ml_probability_to_risk_score(0.5) < 100
    assert ml_probability_to_risk_score(1) <= 100
