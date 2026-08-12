"""决策引擎纯函数测试: 评分公式 / 一票否决 / 档位映射"""
from types import SimpleNamespace

from app.engine.decision import (
    _score_to_decision,
    _score_to_level,
    calculate_final_score,
    check_veto,
)
from app.engine.rule import RuleHitResult


def _hit(score, level):
    return RuleHitResult(SimpleNamespace(
        rule_id="R1", rule_name="规则", rule_category="信贷欺诈",
        risk_score=score, risk_level=level, action="拒绝", description="",
    ))


def test_calculate_final_score():
    assert calculate_final_score([]) == 0
    assert calculate_final_score([_hit(70, "高")]) == 70
    assert calculate_final_score([_hit(70, "高"), _hit(40, "中")]) == 73
    assert calculate_final_score([_hit(95, "极高"), _hit(80, "高"), _hit(70, "高")]) == 100


def test_check_veto():
    assert not check_veto([_hit(70, "高"), _hit(80, "高")])
    assert check_veto([_hit(95, "极高"), _hit(80, "高")])


def test_score_to_level():
    assert _score_to_level(29) == "低"
    assert _score_to_level(59) == "中"
    assert _score_to_level(79) == "高"
    assert _score_to_level(80) == "极高"


def test_score_to_decision():
    assert _score_to_decision(29) == "通过"
    assert _score_to_decision(30) == "标记"
    assert _score_to_decision(59) == "标记"
    assert _score_to_decision(60) == "人工审核"
    assert _score_to_decision(79) == "人工审核"
    assert _score_to_decision(80) == "拒绝"
    assert _score_to_decision(100) == "拒绝"
