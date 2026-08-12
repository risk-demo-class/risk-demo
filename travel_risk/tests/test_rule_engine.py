"""规则引擎单测: 运算符求值 + 嵌套 + 等级分校验"""
import pytest

from app.engine.rule import (
    RuleScoreLevelMismatchError,
    evaluate_condition,
    validate_rule_score_level,
)


@pytest.mark.parametrize("op,value,actual,expected", [
    (">", 10, 15, True),
    (">=", 10, 10, True),
    ("<", 10, 5, True),
    ("<=", 10, 10, True),
    ("==", 1, 1.0, True),
    ("!=", 1, 2, True),
    ("in", [1, 2, 3], 2, True),
    ("not_in", [1, 2, 3], 5, True),
    ("between", [0, 5], 3, True),
])
def test_basic_operators(op, value, actual, expected):
    cond = {"field": "x", "op": op, "value": value}
    assert evaluate_condition(cond, {"x": actual}) is expected


def test_and_nested():
    cond = {"and": [
        {"field": "user_refund_rate", "op": ">=", "value": 0.3},
        {"field": "user_claim_count", "op": ">=", "value": 1},
        {"field": "user_device_count", "op": ">=", "value": 2},
    ]}
    assert evaluate_condition(cond, {"user_refund_rate": 0.5, "user_claim_count": 2, "user_device_count": 3}) is True
    assert evaluate_condition(cond, {"user_refund_rate": 0.1, "user_claim_count": 2, "user_device_count": 3}) is False


def test_or_nested():
    cond = {"or": [
        {"field": "order_total_amount", "op": ">=", "value": 50000},
        {"field": "order_is_night", "op": "==", "value": 1},
    ]}
    assert evaluate_condition(cond, {"order_total_amount": 3000, "order_is_night": 1}) is True
    assert evaluate_condition(cond, {"order_total_amount": 3000, "order_is_night": 0}) is False


def test_unknown_field_returns_false():
    assert evaluate_condition({"field": "ghost", "op": ">", "value": 0}, {"real": 1}) is False


def test_unsupported_op_returns_false():
    assert evaluate_condition({"field": "x", "op": "like", "value": "a"}, {"x": 1}) is False


@pytest.mark.parametrize("level,score", [
    ("低", 10), ("中", 40), ("高", 70), ("极高", 95),
])
def test_validate_rule_score_level_ok(level, score):
    validate_rule_score_level(level, score)  # 不抛异常


@pytest.mark.parametrize("level,score", [
    ("极高", 50), ("高", 30), ("低", 60), ("未知", 60),
])
def test_validate_rule_score_level_mismatch(level, score):
    with pytest.raises(RuleScoreLevelMismatchError):
        validate_rule_score_level(level, score)
