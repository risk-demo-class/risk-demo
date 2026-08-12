"""决策引擎单测: 评分公式 / 一票否决 / 阈值映射 / sigmoid 校准"""
from types import SimpleNamespace

import pytest

from app.config import settings
from app.engine.decision import (
    _ml_prob_to_risk_score,
    _score_to_decision,
    _score_to_level,
    calculate_final_score,
    check_veto,
)
from app.engine.rule import RuleHitResult


def _mock_hit(rid, score, level, action="拒绝"):
    return RuleHitResult(SimpleNamespace(
        rule_id=rid, rule_name=f"规则 {rid}", rule_category="测试",
        risk_score=score, risk_level=level, action=action, description="",
    ))


def test_calculate_final_score_formula():
    assert calculate_final_score([]) == 0
    assert calculate_final_score([_mock_hit("R1", 70, "高")]) == 70
    assert calculate_final_score([_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中")]) == 73
    assert calculate_final_score([_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高")]) == 98


def test_calculate_final_score_cap_100():
    hits = [_mock_hit("R1", 95, "极高") for _ in range(5)]
    assert calculate_final_score(hits) == 100


def test_check_veto():
    assert check_veto([_mock_hit("R1", 70, "高")]) is False
    assert check_veto([_mock_hit("R1", 95, "极高")]) is True


def test_score_to_level_default():
    assert _score_to_level(10) == "低"
    assert _score_to_level(40) == "中"
    assert _score_to_level(70) == "高"
    assert _score_to_level(90) == "极高"


def test_score_to_decision_default():
    assert _score_to_decision(10) == "通过"
    assert _score_to_decision(40) == "标记"
    assert _score_to_decision(70) == "人工审核"
    assert _score_to_decision(90) == "拒绝"


def test_event_thresholds_stricter_for_claim():
    # 理赔申请阈值最严: 同样 70 分, 理赔是"标记", 下单是"人工审核"
    assert _score_to_decision(70, "理赔申请") == "标记"
    assert _score_to_decision(70, "下单") == "人工审核"
    # 同样 85 分, 理赔仍是"人工审核" (review=90), 下单已"拒绝" (review=80)
    assert _score_to_decision(85, "理赔申请") == "人工审核"
    assert _score_to_decision(85, "下单") == "拒绝"


@pytest.mark.parametrize("prob,expected", [
    (0.0, 0), (0.1, 26), (0.3, 59), (0.5, 78), (0.7, 88), (0.9, 93), (1.0, 100),
])
def test_ml_prob_calibration(prob, expected):
    assert _ml_prob_to_risk_score(prob) == expected


def test_config_event_thresholds_fallback():
    th = settings.get_event_thresholds("不存在的类型")
    assert th["pass"] == settings.RISK_PASS_THRESHOLD
