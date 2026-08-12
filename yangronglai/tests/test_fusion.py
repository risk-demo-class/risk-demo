from app.engine.fusion import fuse_scores


def test_fusion_keeps_highest_component_and_weights_corrobation() -> None:
    result = fuse_scores({"rule": 75, "model": 60, "graph": 20}, additional_weight=0.15)
    assert result.primary_component == "rule"
    assert result.primary_score == 75
    assert result.other_components_score_sum == 80
    assert result.raw_score == 87
    assert result.score == 87
    assert result.risk_level == "极高"
    assert result.decision == "拒绝"


def test_fusion_never_weakens_hard_rule_decision() -> None:
    result = fuse_scores(
        {"rule": 60, "model": 10, "graph": 0},
        minimum_decision="拒绝",
        minimum_level="极高",
    )
    assert result.decision == "拒绝"
    assert result.risk_level == "极高"


def test_fusion_caps_at_one_hundred() -> None:
    result = fuse_scores({"rule": 100, "model": 90, "graph": 80})
    assert result.raw_score > 100
    assert result.score == 100
