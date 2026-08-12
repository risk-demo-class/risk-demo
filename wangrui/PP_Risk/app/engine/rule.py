from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_risk import RiskRule


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    rule_name: str
    risk_score: int
    action: str


def _matches(condition: dict[str, object], features: dict[str, float]) -> bool:
    name = str(condition.get("feature", ""))
    if name not in features:
        return False
    actual = features[name]
    expected = float(condition.get("value", 0))
    operator = condition.get("operator", ">=")
    return {
        ">=": actual >= expected,
        ">": actual > expected,
        "<=": actual <= expected,
        "<": actual < expected,
        "==": actual == expected,
    }.get(str(operator), False)


async def match_rules(
    db: AsyncSession, event_type: str, features: dict[str, float]
) -> list[RuleHit]:
    rules = (
        await db.execute(
            select(RiskRule)
            .where(RiskRule.is_enabled.is_(True), RiskRule.event_type.in_((event_type, "通用")))
            .order_by(RiskRule.priority.desc())
        )
    ).scalars()
    hits = []
    for rule in rules:
        condition = json.loads(rule.rule_condition)
        if _matches(condition, features):
            hits.append(RuleHit(rule.rule_id, rule.rule_name, rule.risk_score, rule.action))
    return hits

