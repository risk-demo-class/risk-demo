from types import SimpleNamespace

from app.engine.decision import calculate_final_score, check_veto
from app.engine.rule import RuleHitResult
from app.service.validator import _EVENT_SOURCE_VALIDATORS


def _hit(score: int, level: str) -> RuleHitResult:
    return RuleHitResult(SimpleNamespace(
        rule_id="T", rule_name="test", rule_category="票务欺诈",
        risk_level=level, risk_score=score, action="拒绝", description="",
    ))


def test_pipeline_keeps_core_scoring_contract():
    assert calculate_final_score([_hit(75, "高"), _hit(45, "中")]) == 78


def test_extreme_travel_rule_is_veto():
    assert check_veto([_hit(95, "极高")]) is True


def test_validator_maps_every_travel_event():
    assert set(_EVENT_SOURCE_VALIDATORS) == {"机票预订", "酒店预订", "签证申请", "订单支付"}
