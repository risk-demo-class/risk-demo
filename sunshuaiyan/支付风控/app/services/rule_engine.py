from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import ROOT
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import RiskRule


RULE_PATH = ROOT / "rules" / "pingpong_rules.json"


@dataclass(frozen=True)
class RuleHit:
    id: str
    name: str
    category: str
    severity: str
    score: int
    action: str
    veto: bool
    fraud_scenario: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def load_rules(path: Path = RULE_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rules_from_db(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(RiskRule)
        .where(RiskRule.is_enabled.is_(True))
        .order_by(RiskRule.priority.desc(), RiskRule.rule_id)
    ).all()
    return [
        {
            "id": row.rule_id,
            "name": row.rule_name,
            "stage": row.stage,
            "category": row.category,
            "fraud_scenario": row.fraud_scenario,
            "severity": row.severity,
            "score": row.risk_score,
            "action": row.action,
            "veto": row.is_veto,
            "condition": row.rule_condition,
            "version": row.version,
            "enabled": row.is_enabled,
        }
        for row in rows
    ]


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if actual is None:
        return False
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == ">":
        return float(actual) > float(expected)
    if op == ">=":
        return float(actual) >= float(expected)
    if op == "<":
        return float(actual) < float(expected)
    if op == "<=":
        return float(actual) <= float(expected)
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == "between":
        return float(expected[0]) <= float(actual) <= float(expected[1])
    raise ValueError(f"unsupported operator: {op}")


def evaluate_condition(condition: dict[str, Any], features: dict[str, Any]) -> bool:
    if "and" in condition:
        return all(evaluate_condition(item, features) for item in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(item, features) for item in condition["or"])
    return _compare(features.get(condition["field"]), condition["op"], condition.get("value"))


def evaluate_rules(
    features: dict[str, Any], stage: str = "INBOUND", db: Session | None = None
) -> list[RuleHit]:
    hits: list[RuleHit] = []
    try:
        rules = load_rules_from_db(db) if db is not None else load_rules()
    except SQLAlchemyError:
        rules = load_rules()
    for rule in rules:
        if rule["stage"] != stage:
            continue
        try:
            matched = evaluate_condition(rule["condition"], features)
        except (KeyError, TypeError, ValueError):
            matched = False
        if matched:
            hits.append(
                RuleHit(
                    id=rule["id"],
                    name=rule["name"],
                    category=rule["category"],
                    severity=rule["severity"],
                    score=int(rule["score"]),
                    action=rule["action"],
                    veto=bool(rule["veto"]),
                    fraud_scenario=rule["fraud_scenario"],
                )
            )
    return hits


def aggregate_rule_score(hits: list[RuleHit]) -> int:
    if not hits:
        return 0
    score = max(hit.score for hit in hits) + 3 * (len(hits) - 1)
    if any(hit.veto for hit in hits):
        score = max(score, 90)
    return min(100, score)
