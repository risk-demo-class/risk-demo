"""规则引擎：对教育风控特征执行 JSON 条件表达式。"""

from typing import Any


def evaluate_condition(condition: dict[str, Any], features: dict[str, float]) -> bool:
    """判断一个原子条件或 and/or 组合条件是否命中。"""
    if "and" in condition:
        return all(evaluate_condition(item, features) for item in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(item, features) for item in condition["or"])

    field = condition.get("field")
    operator = condition.get("op")
    if not field or not operator or "value" not in condition:
        return False

    actual = float(features.get(field, 0.0))
    expected = float(condition["value"])
    comparisons = {
        ">": actual > expected,
        ">=": actual >= expected,
        "<": actual < expected,
        "<=": actual <= expected,
        "==": actual == expected,
        "!=": actual != expected,
    }
    return comparisons.get(operator, False)
