from types import SimpleNamespace

import pytest

from app.engine.decision import calculate_decision
from app.engine.ml_model import FEATURE_COLUMNS
from app.engine.rule import (
    InvalidRuleCondition, RULE_MATCHERS, evaluate_condition, match_rules,
    validate_condition,
)


def rule(rule_id="TEST", condition=None, score=50, action="标记", level="中"):
    return SimpleNamespace(
        rule_id=rule_id, rule_name="测试规则", rule_condition=condition,
        risk_level=level, risk_score=score, action=action,
        version=1, enabled=True,
    )


def test_feature_columns_fixed_at_25_unique_dimensions():
    assert len(FEATURE_COLUMNS) == 25
    assert len(set(FEATURE_COLUMNS)) == 25


def test_eight_education_matcher_entries_exist():
    assert set(RULE_MATCHERS) == {"R001", "R002", "R005", "R008", "R012", "R018", "R025", "R030"}


@pytest.mark.parametrize(("condition", "features", "expected"), [
    ({"field": "study_minutes_before_refund", "op": "<", "value": 5}, {"study_minutes_before_refund": 4}, True),
    ({"field": "study_minutes_before_refund", "op": "<", "value": 5}, {"study_minutes_before_refund": 5}, False),
    ({"field": "buyer_paid_amount_1h", "op": ">", "value": 30000}, {"buyer_paid_amount_1h": 30000}, False),
    ({"field": "buyer_paid_amount_1h", "op": ">", "value": 30000}, {"buyer_paid_amount_1h": 30000.01}, True),
    ({"field": "device_student_count", "op": ">=", "value": 5}, {"device_student_count": 4}, False),
    ({"field": "device_student_count", "op": ">=", "value": 5}, {"device_student_count": 5}, True),
    ({"and": [{"field": "session_reward_net_amount", "op": ">", "value": 5000}, {"field": "account_age_days", "op": "<", "value": 30}]}, {"session_reward_net_amount": 5000.01, "account_age_days": 5}, True),
    ({"or": [{"field": "credential_mismatch", "op": "==", "value": 1}, {"field": "credential_no_record", "op": "==", "value": 1}]}, {"credential_no_record": 1}, True),
])
def test_json_rule_boundaries(condition, features, expected):
    assert evaluate_condition(condition, features) is expected


def test_missing_feature_does_not_become_zero():
    condition = {"field": "study_minutes_before_refund", "op": "<", "value": 5}
    assert evaluate_condition(condition, {}) is False


@pytest.mark.parametrize("condition", [
    {},
    {"field": "unknown", "op": ">", "value": 1},
    {"field": "order_total_amount", "op": "evil", "value": 1},
    {"and": []},
    {"field": "order_total_amount", "op": "between", "value": [1]},
])
def test_invalid_conditions_are_rejected(condition):
    with pytest.raises(InvalidRuleCondition):
        validate_condition(condition)


def test_database_fields_are_single_source_of_truth():
    condition = {"field": "study_minutes_before_refund", "op": "<", "value": 3}
    hits = match_rules([rule("R002", condition, score=73, action="标记", level="高")], {"study_minutes_before_refund": 2})
    assert len(hits) == 1
    assert hits[0].risk_score == 73
    assert hits[0].action == "标记"
    result = calculate_decision(hits)
    assert (result.score, result.risk_level, result.decision) == (73, "高", "标记")
