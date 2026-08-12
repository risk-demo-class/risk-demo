from types import SimpleNamespace
from pathlib import Path
import re

import pytest

from app.engine.rule import (
    RuleScoreLevelMismatchError, evaluate_condition, match_rules,
    validate_rule_score_level,
)
from app.engine.ml_model import FEATURE_COLUMNS


def test_scalper_rule_condition():
    assert evaluate_condition(
        {"field": "order_same_flight_count_1h", "op": ">=", "value": 5},
        {"order_same_flight_count_1h": 5},
    )


def test_cross_border_large_order_condition():
    condition = {"and": [
        {"field": "order_is_cross_border", "op": "==", "value": 1},
        {"field": "order_total_amount", "op": ">=", "value": 50000},
    ]}
    assert evaluate_condition(condition, {"order_is_cross_border": 1, "order_total_amount": 60000})
    assert not evaluate_condition(condition, {"order_is_cross_border": 0, "order_total_amount": 60000})


def test_rule_hit_preserves_travel_metadata():
    rule = SimpleNamespace(
        rule_id="TR004", rule_name="黄牛囤票", rule_category="票务欺诈",
        risk_level="极高", risk_score=95, action="拒绝", description="demo",
        condition_dict={"field": "order_same_flight_count_1h", "op": ">=", "value": 5},
    )
    hits = match_rules([rule], {"order_same_flight_count_1h": 8})
    assert hits[0].rule_id == "TR004"


def test_score_level_validation():
    validate_rule_score_level("极高", 95)
    with pytest.raises(RuleScoreLevelMismatchError):
        validate_rule_score_level("高", 45)


def test_seed_rules_only_reference_registered_features():
    sql = (Path(__file__).resolve().parents[1] / "sql" / "init_risk_data.sql").read_text()
    fields = set(re.findall(r'"field":"([^"]+)"', sql))
    assert fields <= set(FEATURE_COLUMNS)
    assert len(set(re.findall(r"'TR\d{3}'", sql))) == 8
