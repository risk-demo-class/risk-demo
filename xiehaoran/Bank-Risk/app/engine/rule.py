"""
规则引擎: 基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

支持的运算符: >, >=, <, <=, ==, !=, in, not_in, between, and, or
银行语义移植自 AI_Risk, 规则从 DB 读取 (risk_rule 表).
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_risk import RiskRule

logger = logging.getLogger(__name__)


class RuleScoreLevelMismatchError(ValueError):
    """风险等级跟分数不匹配 (业务校验失败)."""


def validate_rule_score_level(risk_level: str, risk_score: int) -> None:
    if risk_level not in settings.RISK_LEVEL_SCORE_MAP:
        raise RuleScoreLevelMismatchError(
            f"未知风险等级: {risk_level}, 应该是 {list(settings.RISK_LEVEL_SCORE_MAP.keys())} 之一"
        )
    if not isinstance(risk_score, int) or not (0 <= risk_score <= 100):
        raise RuleScoreLevelMismatchError(f"risk_score 必须是 0-100 整数, 当前 {risk_score!r}")
    low, high = settings.RISK_LEVEL_SCORE_MAP[risk_level]
    if not (low <= risk_score <= high):
        raise RuleScoreLevelMismatchError(
            f"风险等级 {risk_level} 对应分数区间 [{low}, {high}], 当前 risk_score={risk_score} 越界"
        )


class RuleHitResult:
    """单条规则"命中"结果."""

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


def match_rules(rules: list[RiskRule], features: dict[str, float]) -> list[RuleHitResult]:
    hits: list[RuleHitResult] = []
    for rule in rules:
        try:
            condition = rule.condition_dict
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("规则 %s 条件解析失败: %s", rule.rule_id, e)
            continue
        if evaluate_condition(condition, features):
            hits.append(RuleHitResult(rule))
    return hits


def evaluate_condition(condition: dict, features: dict[str, float]) -> bool:
    if "and" in condition:
        return all(evaluate_condition(sub, features) for sub in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(sub, features) for sub in condition["or"])

    field = condition.get("field", "")
    op = condition.get("op", "")
    value = condition.get("value")

    actual = features.get(field)
    if actual is None:
        return False
    try:
        return _compare(actual, op, value)
    except Exception as e:
        logger.warning("条件求值异常: field=%s, op=%s, value=%s, actual=%s, err=%s",
                       field, op, value, actual, e)
        return False


def _compare(actual: float, op: str, value: Any) -> bool:
    if op == ">":    return actual > float(value)
    elif op == ">=": return actual >= float(value)
    elif op == "<":  return actual < float(value)
    elif op == "<=": return actual <= float(value)
    elif op == "==": return actual == float(value)
    elif op == "!=": return actual != float(value)
    elif op == "in":     return actual in [float(v) for v in value]
    elif op == "not_in": return actual not in [float(v) for v in value]
    elif op == "between":
        low, high = float(value[0]), float(value[1])
        return low <= actual <= high
    else:
        logger.warning("不支持的运算符: %s", op)
        return False


async def load_enabled_rules(db: AsyncSession, event_type: str | None = None) -> list[RiskRule]:
    stmt = select(RiskRule).where(
        RiskRule.is_enabled == 1,
        RiskRule.deleted_at.is_(None),
    )
    if event_type:
        stmt = stmt.where(RiskRule.event_type.in_([event_type, "通用"]))
    stmt = stmt.order_by(RiskRule.priority.desc())
    return list((await db.execute(stmt)).scalars().all())
