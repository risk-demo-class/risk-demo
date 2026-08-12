from types import SimpleNamespace

from app.engine.decision import (
    _score_to_decision,
    _score_to_level,
    calculate_final_score,
    check_veto,
)


def _hit(score, action="标记"):
    return SimpleNamespace(
        risk_score=score,
        action=action,
        risk_level="极高" if action == "拒绝" else "高",
    )


def test_rule_scores_are_capped_and_veto_works():
    hits = [_hit(75), _hit(60, "拒绝")]
    # 多规则算法取最高分，并按额外命中数增加配置中的 3 分奖励。
    assert calculate_final_score(hits) == 78
    assert check_veto(hits) is True


def test_transfer_policy_is_sensitive():
    assert _score_to_decision(19, "转账") == "通过"
    assert _score_to_decision(20, "转账") == "标记"
    assert _score_to_decision(75, "转账") == "拒绝"
    assert _score_to_level(86, "转账") == "极高"
