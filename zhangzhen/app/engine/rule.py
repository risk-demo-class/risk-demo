"""JSON 条件树求值与规则匹配。"""

import json
import logging
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleEventType
from app.models_risk import RiskRule
from app.schemas import TriggeredRule


logger = logging.getLogger(__name__)


def _logical_children(condition: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
    direct = condition.get(key)
    if isinstance(direct, list):
        return direct
    if str(condition.get("op", "")).lower() == key:
        children = condition.get("conditions")
        if isinstance(children, list):
            return children
    return None


def evaluate_condition(condition: dict[str, Any], features: dict[str, float]) -> bool:
    """递归执行单条件、AND 和 OR；坏规则只返回未命中。"""

    try:
        and_children = _logical_children(condition, "and")
        if and_children is not None:
            return bool(and_children) and all(
                evaluate_condition(child, features) for child in and_children
            )

        or_children = _logical_children(condition, "or")
        if or_children is not None:
            return bool(or_children) and any(
                evaluate_condition(child, features) for child in or_children
            )

        field = condition.get("field")
        operator = condition.get("op")
        expected = condition.get("value")
        if not isinstance(field, str) or field not in features:
            return False
        actual = features[field]

        if operator == ">":
            return actual > expected
        if operator == ">=":
            return actual >= expected
        if operator == "<":
            return actual < expected
        if operator == "<=":
            return actual <= expected
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == "in":
            return actual in expected
        if operator == "not_in":
            return actual not in expected
        if operator == "between":
            return (
                isinstance(expected, (list, tuple))
                and len(expected) == 2
                and expected[0] <= actual <= expected[1]
            )
        return False
    except (TypeError, ValueError, KeyError):
        logger.warning("规则条件无法求值，按未命中处理", extra={"condition": condition})
        return False


def condition_fields(condition: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    field = condition.get("field")
    if isinstance(field, str):
        fields.add(field)
    for key in ("and", "or", "conditions"):
        children = condition.get(key)
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    fields.update(condition_fields(child))
    return fields


def normalize_condition(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


async def load_active_rules(
    db: AsyncSession,
    event_type: RuleEventType,
) -> Sequence[RiskRule]:
    result = await db.execute(
        select(RiskRule)
        .where(
            RiskRule.deleted_at.is_(None),
            RiskRule.is_enabled.is_(True),
            or_(
                RiskRule.event_type == event_type,
                RiskRule.event_type == RuleEventType.COMMON,
            ),
        )
        .order_by(RiskRule.priority.desc(), RiskRule.rule_id.asc())
    )
    return result.scalars().all()


def match_rules(
    rules: Iterable[RiskRule],
    features: dict[str, float],
) -> list[TriggeredRule]:
    triggered: list[TriggeredRule] = []
    for rule in rules:
        condition = normalize_condition(rule.rule_condition)
        if condition is None:
            logger.warning("规则JSON损坏，已跳过", extra={"rule_id": rule.rule_id})
            continue
        if not evaluate_condition(condition, features):
            continue
        actual_values = {
            field: features[field]
            for field in sorted(condition_fields(condition))
            if field in features
        }
        triggered.append(
            TriggeredRule(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                risk_level=rule.risk_level,
                risk_score=rule.risk_score,
                action=rule.action,
                condition=condition,
                actual_values=actual_values,
            )
        )
    return triggered

