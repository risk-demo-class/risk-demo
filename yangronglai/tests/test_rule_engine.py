from types import SimpleNamespace

import pytest

from app.engine.rule import evaluate_condition, rule_engine
from app.engine.rule_catalog import RULE_CATALOG


def test_condition_language_supports_field_to_field_comparison() -> None:
    condition = {"field": "current_city", "op": "!=", "value_field": "usual_city"}
    assert evaluate_condition(condition, {"current_city": "上海", "usual_city": "北京"})
    assert not evaluate_condition(condition, {"current_city": "北京", "usual_city": "北京"})
    assert not evaluate_condition(condition, {"current_city": None, "usual_city": "北京"})


def test_rule_engine_uses_strongest_decision_and_max_score() -> None:
    rules = [SimpleNamespace(**rule) for rule in RULE_CATALOG if rule["rule_id"] in {"R001", "R005"}]
    features = {
        "amount": 60001,
        "current_city": "上海",
        "usual_city": "北京",
        "device_age_days": 2,
    }
    evaluation = rule_engine.evaluate(features, rules)
    assert evaluation.score == 100
    assert evaluation.decision == "拒绝"
    assert {hit.rule_id for hit in evaluation.hits} == {"R001", "R005"}


def test_multiple_rules_add_weighted_secondary_scores() -> None:
    rules = [SimpleNamespace(**rule) for rule in RULE_CATALOG if rule["rule_id"] in {"R002", "R005"}]
    features = {
        "event_hour": 2,
        "transactions_1h": 3,
        "device_age_days": 2,
        "amount": 40000,
    }
    evaluation = rule_engine.evaluate(features, rules, additional_weight=0.2)
    assert evaluation.highest_rule_score == 75
    assert evaluation.other_rules_score_sum == 70
    assert evaluation.weighted_addition == 14
    assert evaluation.raw_score == 89
    assert evaluation.score == 89
    assert evaluation.risk_level == "极高"
    assert evaluation.decision == "拒绝"


def test_equal_secondary_rule_is_weighted_and_total_is_capped() -> None:
    rules = [SimpleNamespace(**rule) for rule in RULE_CATALOG if rule["rule_id"] in {"R001", "R005"}]
    features = {
        "amount": 60001,
        "current_city": "上海",
        "usual_city": "北京",
        "device_age_days": 2,
    }
    evaluation = rule_engine.evaluate(features, rules, additional_weight=0.2)
    assert evaluation.raw_score == 115
    assert evaluation.score == 100


def test_additional_weight_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValueError, match="additional_weight"):
        rule_engine.evaluate({}, [], additional_weight=1.1)


@pytest.mark.parametrize("rule", RULE_CATALOG, ids=lambda item: item["rule_id"])
def test_catalog_rules_have_auditable_metadata(rule: dict) -> None:
    assert 0 <= rule["risk_score"] <= 100
    assert rule["decision"] in {"通过", "标记", "人工审核", "拒绝"}
    assert rule["risk_level"] in {"低", "中", "高", "极高"}
    assert rule["description"]
