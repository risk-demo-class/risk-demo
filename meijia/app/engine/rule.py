"""数据库驱动的通用规则引擎。

数据库中的 rule_condition、risk_score 和 action 是唯一事实来源。Engine 不依赖 HTTP。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.engine.ml_model import FEATURE_COLUMNS
from app.models_risk import RiskRule

FeatureMap = dict[str, float]
SUPPORTED_OPERATORS = {">", ">=", "<", "<=", "==", "!=", "in", "not_in", "between"}


class InvalidRuleCondition(ValueError):
    """规则 JSON 结构、字段或运算符无效。"""


def validate_condition(condition: Any) -> None:
    """递归校验条件结构；保存规则前和执行规则时都可调用。"""
    if not isinstance(condition, dict) or not condition:
        raise InvalidRuleCondition("规则条件必须是非空对象")
    logical_keys = [key for key in ("and", "or") if key in condition]
    if logical_keys:
        if len(logical_keys) != 1 or len(condition) != 1:
            raise InvalidRuleCondition("逻辑条件只能包含一个 and 或 or")
        children = condition[logical_keys[0]]
        if not isinstance(children, list) or not children:
            raise InvalidRuleCondition(f"{logical_keys[0]} 必须是非空条件数组")
        for child in children:
            validate_condition(child)
        return

    if set(condition) != {"field", "op", "value"}:
        raise InvalidRuleCondition("叶子条件必须且只能包含 field、op、value")
    field, operator, value = condition["field"], condition["op"], condition["value"]
    if field not in FEATURE_COLUMNS:
        raise InvalidRuleCondition(f"未知特征字段: {field}")
    if operator not in SUPPORTED_OPERATORS:
        raise InvalidRuleCondition(f"不支持的运算符: {operator}")
    if operator in {"in", "not_in"} and not isinstance(value, list):
        raise InvalidRuleCondition(f"{operator} 的 value 必须是数组")
    if operator == "between" and (not isinstance(value, list) or len(value) != 2):
        raise InvalidRuleCondition("between 的 value 必须是两个元素的数组")


def evaluate_condition(condition: dict, features: FeatureMap) -> bool:
    """递归求值。特征缺失时返回 False，不把缺失误当成数值 0。"""
    validate_condition(condition)
    if "and" in condition:
        return all(evaluate_condition(child, features) for child in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(child, features) for child in condition["or"])

    actual = features.get(condition["field"])
    if actual is None:
        return False
    return compare(actual, condition["op"], condition["value"])


def compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == ">": return actual > expected
    if operator == ">=": return actual >= expected
    if operator == "<": return actual < expected
    if operator == "<=": return actual <= expected
    if operator == "==": return actual == expected
    if operator == "!=": return actual != expected
    if operator == "in": return actual in expected
    if operator == "not_in": return actual not in expected
    if operator == "between": return expected[0] <= actual <= expected[1]
    raise InvalidRuleCondition(f"不支持的运算符: {operator}")


# 保留任务 2 的“每条规则一个 match 函数”接口，但全部委托给数据库条件求值器，
# 不在 Python 中重复保存阈值。
def match_r001(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r002(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r005(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r008(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r012(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r018(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r025(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)
def match_r030(condition: dict, features: FeatureMap) -> bool: return evaluate_condition(condition, features)

RULE_MATCHERS = {
    "R001": match_r001, "R002": match_r002, "R005": match_r005, "R008": match_r008,
    "R012": match_r012, "R018": match_r018, "R025": match_r025, "R030": match_r030,
}


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    rule_name: str
    risk_level: str
    risk_score: int
    action: str
    version: int
    condition: dict

    def to_dict(self) -> dict:
        return asdict(self)


def load_enabled_rules(db: Session, event_type: str | None = None) -> list[RiskRule]:
    stmt = select(RiskRule).where(RiskRule.enabled.is_(True), RiskRule.deleted_at.is_(None))
    if event_type:
        stmt = stmt.where(or_(RiskRule.event_type == event_type, RiskRule.event_type == "通用"))
    return list(db.scalars(stmt.order_by(RiskRule.priority.desc(), RiskRule.rule_id)))


def match_rules(rules: list[RiskRule], features: FeatureMap) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for rule in rules:
        if not rule.enabled:
            continue
        matcher = RULE_MATCHERS.get(rule.rule_id, evaluate_condition)
        if matcher(rule.rule_condition, features):
            hits.append(RuleHit(
                rule_id=rule.rule_id, rule_name=rule.rule_name,
                risk_level=rule.risk_level, risk_score=rule.risk_score,
                action=rule.action, version=rule.version,
                condition=rule.rule_condition,
            ))
    return hits


def decide(hits: list[RuleHit]) -> tuple[int, str, str]:
    """兼容旧调用；新代码优先使用 engine.decision.calculate_decision。"""
    from app.engine.decision import calculate_decision

    result = calculate_decision(hits)
    return result.score, result.risk_level, result.decision


def demo() -> None:
    condition = {"field": "study_minutes_before_refund", "op": "<", "value": 5}
    assert evaluate_condition(condition, {"study_minutes_before_refund": 2})
    assert not evaluate_condition(condition, {"study_minutes_before_refund": 5})
    print("rule demo OK: JSON condition is the single source of truth")


if __name__ == "__main__":
    demo()
