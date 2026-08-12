"""可配置规则加载与纯计算匹配。"""
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_risk import RiskRule


@dataclass(frozen=True)
class RuleHitResult:
    rule_id: str
    rule_name: str
    rule_category: str
    risk_level: str
    risk_score: int
    action: str
    description: str | None = None

    @classmethod
    def from_rule(cls, rule: RiskRule) -> "RuleHitResult":
        return cls(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            rule_category=rule.rule_category,
            risk_level=rule.risk_level,
            risk_score=rule.risk_score,
            action=rule.action,
            description=rule.description,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _compare(actual: float, operator: str, expected: Any) -> bool:
    operations = {
        ">": lambda: actual > expected,
        ">=": lambda: actual >= expected,
        "<": lambda: actual < expected,
        "<=": lambda: actual <= expected,
        "==": lambda: actual == expected,
        "!=": lambda: actual != expected,
        "in": lambda: actual in expected,
    }
    if operator not in operations:
        raise ValueError(f"不支持的规则运算符: {operator}")
    return bool(operations[operator]())


def evaluate_condition(condition: dict[str, Any], features: dict[str, float]) -> bool:
    if "all" in condition:
        return all(evaluate_condition(item, features) for item in condition["all"])
    if "any" in condition:
        return any(evaluate_condition(item, features) for item in condition["any"])
    feature = condition["feature"]
    return _compare(features.get(feature, 0), condition["op"], condition["value"])


def match_rules(rules: list[RiskRule], features: dict[str, float]) -> list[RuleHitResult]:
    hits = []
    for rule in rules:
        condition = rule.condition_dict if hasattr(rule, "condition_dict") else json.loads(rule.rule_condition)
        if evaluate_condition(condition, features):
            hits.append(RuleHitResult.from_rule(rule))
    return hits


async def load_enabled_rules(db: AsyncSession, event_type: str) -> list[RiskRule]:
    result = await db.execute(
        select(RiskRule)
        .where(
            RiskRule.is_enabled == 1,
            RiskRule.deleted_at.is_(None),
            or_(RiskRule.event_type == event_type, RiskRule.event_type == "通用"),
        )
        .order_by(RiskRule.priority.desc(), RiskRule.rule_id)
    )
    return list(result.scalars().all())
