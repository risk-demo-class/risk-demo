from types import SimpleNamespace

import pytest

from app.engine.decision import (
    calculate_final_score,
    has_veto,
    score_to_decision,
    score_to_level,
)
from app.engine.feature import FEATURE_COLUMNS
from app.engine.rule import RuleHitResult, evaluate_condition, match_rules
from app.engine.rule_definitions import BLACKLIST_RULE, RULE_DEFINITIONS


def _hit(score: int, level: str = "高") -> RuleHitResult:
    return RuleHitResult("X", "测试", "通用", level, score, "人工审核")


def test_feature_contract_is_exactly_25_unique_columns():
    assert len(FEATURE_COLUMNS) == 25
    assert len(set(FEATURE_COLUMNS)) == 25
    assert all(name.startswith(("patient_", "event_", "prescription_", "claim_", "doctor_", "hospital_", "device_")) for name in FEATURE_COLUMNS)


def test_sixteen_rule_contract_and_feature_references():
    assert len(RULE_DEFINITIONS) == 15
    assert BLACKLIST_RULE["rule_id"] == "MR016"

    def referenced(condition):
        if "feature" in condition:
            return {condition["feature"]}
        return set().union(*(referenced(item) for item in condition.get("all", condition.get("any", []))))

    for definition in RULE_DEFINITIONS:
        assert referenced(definition[4]) <= set(FEATURE_COLUMNS)


def test_rule_condition_all_any_and_comparisons():
    features = {"x": 10, "y": 2}
    assert evaluate_condition({"all": [
        {"feature": "x", "op": ">=", "value": 10},
        {"feature": "y", "op": "<", "value": 3},
    ]}, features)
    assert evaluate_condition({"any": [
        {"feature": "x", "op": "==", "value": 1},
        {"feature": "y", "op": "!=", "value": 3},
    ]}, features)
    with pytest.raises(ValueError):
        evaluate_condition({"feature": "x", "op": "exec", "value": 1}, features)


def test_score_mapping_bonus_cap_and_veto():
    assert calculate_final_score([]) == 0
    assert calculate_final_score([_hit(70), _hit(40), _hit(20)]) == 76
    assert calculate_final_score([_hit(99), _hit(80)]) == 100
    assert has_veto([_hit(95, "极高")])
    assert [score_to_decision(x) for x in (0, 30, 60, 80)] == ["通过", "标记", "人工审核", "拒绝"]
    assert [score_to_level(x) for x in (0, 30, 60, 80)] == ["低", "中", "高", "极高"]


def test_match_rules_returns_explainable_hit():
    rule = SimpleNamespace(
        rule_id="MRX", rule_name="测试规则", rule_category="通用",
        risk_level="高", risk_score=75, action="人工审核", description="说明",
        condition_dict={"feature": "event_total_amount", "op": ">=", "value": 100},
    )
    hits = match_rules([rule], {"event_total_amount": 101})
    assert hits[0].to_dict()["rule_id"] == "MRX"
