from app.engine.rule_seed import PRESET_RULES
from app.models import RiskLevel


def test_preset_rule_contract() -> None:
    assert len(PRESET_RULES) == 20
    assert len({rule["rule_id"] for rule in PRESET_RULES}) == 20
    assert sum(rule["risk_level"] is RiskLevel.EXTREME for rule in PRESET_RULES) >= 3
    assert sum(
        "and" in rule["rule_condition"] or "or" in rule["rule_condition"]
        for rule in PRESET_RULES
    ) >= 4

