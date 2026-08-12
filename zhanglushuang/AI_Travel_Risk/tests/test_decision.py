"""决策引擎纯函数测试."""

from types import SimpleNamespace

from app.engine.decision import (
    calculate_final_score,
    check_veto,
    _score_to_decision,
    _score_to_level,
)
from app.engine.rule import RuleHitResult


def _hit(rid, score, level):
    return RuleHitResult(
        SimpleNamespace(
            rule_id=rid,
            rule_name=rid,
            rule_category="订单欺诈",
            risk_level=level,
            risk_score=score,
            action="人工审核",
            description="",
        )
    )


def test_score_mapping():
    assert _score_to_level(20) == "低"
    assert _score_to_level(50) == "中"
    assert _score_to_level(70) == "高"
    assert _score_to_level(90) == "极高"
    assert _score_to_decision(20) == "通过"
    assert _score_to_decision(50) == "标记"
    assert _score_to_decision(70) == "人工审核"
    assert _score_to_decision(90) == "拒绝"


def test_calculate_final_score():
    assert calculate_final_score([]) == 0
    assert calculate_final_score([_hit("R1", 70, "高")]) == 70
    assert calculate_final_score([_hit("R1", 70, "高"), _hit("R2", 40, "中")]) == 73


def test_check_veto():
    assert not check_veto([_hit("R1", 70, "高")])
    assert check_veto([_hit("R1", 70, "高"), _hit("R2", 95, "极高")])
