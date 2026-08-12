"""
规则引擎.

基于 JSON 条件表达式对特征字典求值, 支持 14 种运算符.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskRule

logger = logging.getLogger(__name__)


class RuleHitResult:
    """单条规则命中结果."""

    def __init__(self, rule: RiskRule):
        self.rule_id = rule.rule_id
        self.rule_name = rule.rule_name
        self.rule_category = rule.rule_category
        self.risk_level = rule.risk_level
        self.risk_score = rule.risk_score
        self.action = rule.action
        self.description = rule.description

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_category": self.rule_category,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "action": self.action,
            "description": self.description,
        }


def evaluate_condition(condition: dict, features: dict[str, float]) -> bool:
    """递归求值 JSON 条件表达式."""
    try:
        if "and" in condition:
            return all(evaluate_condition(sub, features) for sub in condition["and"])
        if "or" in condition:
            return any(evaluate_condition(sub, features) for sub in condition["or"])

        field = condition.get("field", "")
        op = condition.get("op", "")
        value = condition.get("value")
        actual = features.get(field)
        if actual is None:
            logger.debug("特征不存在, 规则不命中: field=%s", field)
            return False
        return _compare(actual, op, value)
    except Exception:
        logger.exception("规则条件求值异常: condition=%s", condition)
        return False


def _compare(actual: float, op: str, value: Any) -> bool:
    """执行单次比较, 未知 op 兜底 False."""
    if op == ">":
        return actual > float(value)
    if op == ">=":
        return actual >= float(value)
    if op == "<":
        return actual < float(value)
    if op == "<=":
        return actual <= float(value)
    if op == "==":
        return actual == float(value)
    if op == "!=":
        return actual != float(value)
    if op == "in":
        return actual in [float(v) for v in value]
    if op == "not_in":
        return actual not in [float(v) for v in value]
    if op == "between":
        low, high = float(value[0]), float(value[1])
        return low <= actual <= high
    logger.warning("不支持的运算符: %s", op)
    return False


def match_rules(
    rules: list[RiskRule],
    features: dict[str, float],
) -> list[RuleHitResult]:
    """对规则列表求值, 返回所有命中."""
    hits: list[RuleHitResult] = []
    for rule in rules:
        try:
            condition = rule.condition_dict
            if evaluate_condition(condition, features):
                logger.info(
                    "规则命中: %s (%s), score=%d, level=%s",
                    rule.rule_id,
                    rule.rule_name,
                    rule.risk_score,
                    rule.risk_level,
                )
                hits.append(RuleHitResult(rule))
        except Exception:
            logger.exception("规则求值失败: rule_id=%s", rule.rule_id)
    return hits


async def load_enabled_rules(
    db: AsyncSession,
    event_type: str | None = None,
) -> list[RiskRule]:
    """加载启用且未软删的规则, 按优先级降序."""
    try:
        stmt = select(RiskRule).where(
            RiskRule.is_enabled == 1,
            RiskRule.deleted_at.is_(None),
        )
        if event_type:
            stmt = stmt.where(RiskRule.event_type.in_([event_type, "通用"]))
        stmt = stmt.order_by(RiskRule.priority.desc())
        return list((await db.execute(stmt)).scalars().all())
    except Exception:
        logger.exception("加载规则失败: event_type=%s", event_type)
        raise
