import pytest

from app.engine.rule import evaluate_condition


@pytest.mark.parametrize(
    ("operator", "expected", "result"),
    [
        (">", 9, True),
        (">=", 10, True),
        ("<", 11, True),
        ("<=", 10, True),
        ("==", 10, True),
        ("!=", 9, True),
        ("in", [8, 9, 10], True),
        ("not_in", [1, 2, 3], True),
        ("between", [5, 15], True),
    ],
)
def test_all_comparison_operators(operator, expected, result) -> None:
    condition = {"field": "txn_amount", "op": operator, "value": expected}

    assert evaluate_condition(condition, {"txn_amount": 10}) is result


def test_nested_and_or_conditions() -> None:
    condition = {
        "and": [
            {"field": "txn_amount", "op": ">=", "value": 50000},
            {
                "or": [
                    {"field": "ip_is_proxy", "op": "==", "value": 1},
                    {"field": "ip_is_tor", "op": "==", "value": 1},
                ]
            },
        ]
    }

    assert evaluate_condition(condition, {"txn_amount": 60000, "ip_is_proxy": 1, "ip_is_tor": 0})


def test_unknown_field_or_operator_is_not_a_match() -> None:
    assert not evaluate_condition({"field": "missing", "op": ">", "value": 1}, {})
    assert not evaluate_condition({"field": "txn_amount", "op": "???", "value": 1}, {"txn_amount": 2})

