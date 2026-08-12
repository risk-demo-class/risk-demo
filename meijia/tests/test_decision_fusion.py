"""双轨决策融合单测: 规则分/bonus、一票否决、ML 融合数学、兼容旧行为。"""

from __future__ import annotations

from types import SimpleNamespace

from app.engine.decision import (
    DecisionResult, _ml_prob_to_risk_score, calculate_decision,
    calculate_rule_score, check_veto,
)


def rule(rule_id="TEST", score=50, action="标记", level="中"):
    return SimpleNamespace(
        rule_id=rule_id, rule_name="测试规则", rule_condition={},
        risk_level=level, risk_score=score, action=action,
        version=1, enabled=True,
    )


def ml(prob, decision, is_loaded=True):
    return SimpleNamespace(score=prob, decision=decision, is_loaded=is_loaded)


def test_calculate_rule_score_bonus_and_cap():
    assert calculate_rule_score([]) == 0
    assert calculate_rule_score([rule(score=70)]) == 70
    assert calculate_rule_score([rule(score=70), rule(score=40), rule(score=20)]) == 76
    assert calculate_rule_score([rule(score=95), rule(score=80), rule(score=70)]) == 100


def test_check_veto():
    assert check_veto([rule(score=50, level="高")]) is False
    assert check_veto([rule(score=50, level="极高")]) is True


def test_calibration_points():
    import math

    expected = {p: 100.0 * (1.0 - math.exp(-3.0 * p)) for p in (0.1, 0.5, 0.9)}
    for prob, target in expected.items():
        assert abs(_ml_prob_to_risk_score(prob) - target) < 1e-6


def test_rule_only_backward_compat():
    # 不带 ml 时行为与旧版一致: 取最严 action, 90/70/40 等级
    r = calculate_decision([rule(rule_id="R002", score=73, action="标记", level="高")])
    assert (r.score, r.risk_level, r.decision) == (73, "高", "标记")
    assert r.ml_score is None and r.ml_decision is None

    empty = calculate_decision([])
    assert (empty.score, empty.risk_level, empty.decision) == (0, "低", "通过")


def test_ml_fusion_math():
    # rule_score=70 (标记), ml 0.5→78分 → final = round(0.5*70+0.5*78)=74
    # 决策取两轨更严: 标记 vs 人工审核 → 人工审核
    r = calculate_decision([rule(score=70, action="标记", level="高")],
                           ml=ml(0.5, "人工审核"))
    assert r.score == 74
    assert r.risk_level == "高"
    assert r.decision == "人工审核"
    assert r.ml_score == 0.5
    assert r.ml_decision == "人工审核"


def test_ml_not_loaded_is_ignored():
    # is_loaded=False → 走纯规则, ml 字段落空
    r = calculate_decision([rule(score=70, action="标记", level="高")],
                           ml=ml(0.5, "拒绝", is_loaded=False))
    assert (r.score, r.risk_level, r.decision) == (70, "高", "标记")
    assert r.ml_score is None


def test_ml_no_rule_can_still_flag():
    # 无规则命中但 ML 给出 人工审核 → 仍要人工审核
    r = calculate_decision([], ml=ml(0.5, "人工审核"))
    assert r.decision == "人工审核"
    assert r.ml_score == 0.5


def test_veto_overrides_ml():
    # 极高规则命中 + ML 说通过 → 仍然拒绝, 分数推到 VETO_MIN
    hits = [rule(rule_id="R001", score=100, action="拒绝", level="极高")]
    r = calculate_decision(hits, ml=ml(0.1, "通过"))
    assert r.decision == "拒绝"
    assert r.risk_level == "极高"
    assert r.score >= 90
