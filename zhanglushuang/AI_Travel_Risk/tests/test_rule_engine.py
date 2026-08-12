"""规则引擎测试."""

from app.engine.rule import evaluate_condition


def test_single_condition():
    assert evaluate_condition(
        {"field": "order_total_amount", "op": ">=", "value": 5000},
        {"order_total_amount": 8000},
    )


def test_and_condition():
    condition = {
        "and": [
            {"field": "order_is_night", "op": "==", "value": 1},
            {"field": "order_trip_days", "op": "<", "value": 7},
        ]
    }
    features = {"order_is_night": 1, "order_trip_days": 3}
    assert evaluate_condition(condition, features)


def test_or_condition():
    condition = {
        "or": [
            {"field": "user_visa_reject_90d", "op": ">=", "value": 2},
            {"field": "remark_llm_score", "op": ">=", "value": 80},
        ]
    }
    features = {"user_visa_reject_90d": 0, "remark_llm_score": 90}
    assert evaluate_condition(condition, features)


def test_unknown_field_returns_false():
    assert not evaluate_condition(
        {"field": "ghost_feature", "op": ">", "value": 1},
        {"order_total_amount": 10},
    )


def test_unknown_op_returns_false():
    assert not evaluate_condition(
        {"field": "order_total_amount", "op": "like", "value": 1},
        {"order_total_amount": 10},
    )
