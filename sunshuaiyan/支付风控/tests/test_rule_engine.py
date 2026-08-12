from __future__ import annotations

from app.services.rule_engine import (
    RuleHit,
    aggregate_rule_score,
    evaluate_condition,
    evaluate_rules,
    load_rules,
)


def test_rule_catalog_has_36_unique_rules() -> None:
    rules = load_rules()
    assert len(rules) == 36
    assert len({rule["id"] for rule in rules}) == 36
    assert {rule["stage"] for rule in rules} == {
        "ONBOARDING",
        "INBOUND",
        "FX",
        "PAYOUT",
        "REFUND",
    }


def test_nested_condition_evaluation() -> None:
    condition = {
        "and": [
            {"field": "amount_usd", "op": ">=", "value": 50_000},
            {
                "or": [
                    {"field": "is_first_payer", "op": "==", "value": 1},
                    {"field": "payer_external_risk_flag", "op": "==", "value": 1},
                ]
            },
        ]
    }
    assert evaluate_condition(condition, {"amount_usd": 80_000, "is_first_payer": 1})
    assert not evaluate_condition(condition, {"amount_usd": 10_000, "is_first_payer": 1})


def test_inbound_rules_match_known_sanctions_veto() -> None:
    hits = evaluate_rules({"payer_sanctions_flag": 1}, stage="INBOUND")
    assert any(hit.id == "PP-R015" and hit.veto for hit in hits)
    assert aggregate_rule_score(hits) >= 90


def test_veto_enforces_minimum_score() -> None:
    hit = RuleHit(
        id="T-1",
        name="test",
        category="TEST",
        severity="CRITICAL",
        score=10,
        action="REJECT",
        veto=True,
        fraud_scenario="test",
    )
    assert aggregate_rule_score([hit]) == 90
