import json
from types import SimpleNamespace

import numpy as np
import pytest

from app.engine.decision import calculate_fused_score
from app.engine.feature import FEATURE_COLUMNS
from app.engine.ml_model import MlResult, features_to_matrix
from app.engine.rule import RuleHitResult
from app.engine.training_data import weak_supervision_label


def _hit(level="高", score=75, action="人工审核"):
    return RuleHitResult("T1", "测试规则", "通用", level, score, action)


def test_model_matrix_strictly_follows_25_feature_columns():
    features = {name: index + 0.5 for index, name in enumerate(reversed(FEATURE_COLUMNS))}
    matrix = features_to_matrix(features)
    assert matrix.shape == (1, 25)
    assert matrix.dtype == np.float32
    assert matrix[0, 0] == pytest.approx(features[FEATURE_COLUMNS[0]])


def test_missing_model_keeps_pure_rule_score():
    assert calculate_fused_score(75, [_hit()], MlResult(None, None, False)) == 75


def test_fusion_never_downgrades_rule_action_below_review_boundary():
    score = calculate_fused_score(75, [_hit()], MlResult(0.01, "通过", True))
    assert score >= 60


def test_weak_supervision_uses_features_but_does_not_extend_feature_contract():
    features = {name: 0.0 for name in FEATURE_COLUMNS}
    features["event_total_amount"] = 25000
    label, rules = weak_supervision_label("医保结算", features)
    assert label == 1
    assert "MR003" in rules
    assert "label" not in FEATURE_COLUMNS
    assert "rule_result" not in FEATURE_COLUMNS
