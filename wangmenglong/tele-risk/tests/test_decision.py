"""
决策引擎测试 (无需 DB): 评分公式 + 一票否决 + 双轨融合 + 等级/决策映射.

覆盖 calculate_final_score / check_veto / _score_to_level / _score_to_decision /
_calculate_decision (含 ML mock + veto 双保险).
"""
from types import SimpleNamespace

import pytest

from app.engine.decision import (
    _calculate_decision, _ml_prob_to_risk_score, _score_to_decision,
    _score_to_level, calculate_final_score, check_veto,
)
from app.engine.rule import RuleHitResult


def _mock_hit(rid, score, level, action="关停号码"):
    """造 1 个 RuleHitResult (不依赖 ORM)."""
    return RuleHitResult(SimpleNamespace(
        rule_id=rid, rule_name=f"规则{rid}", rule_category="测试",
        risk_score=score, risk_level=level, action=action, description="",
    ))


# ============================================================
# 1. 评分公式: max(规则分) + 3 × (额外命中数), 上限 100
# ============================================================

class TestFinalScore:
    def test_single_hit(self):
        assert calculate_final_score([_mock_hit("R1", 70, "高")]) == 70

    def test_multi_hit_with_bonus(self):
        hits = [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中"), _mock_hit("R3", 20, "低")]
        # 70 + 2*3 = 76
        assert calculate_final_score(hits) == 76

    def test_cap_at_100(self):
        hits = [_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高"), _mock_hit("R3", 70, "高")]
        # 95 + 2*3 = 101 → 100
        assert calculate_final_score(hits) == 100

    def test_empty_hits(self):
        assert calculate_final_score([]) == 0


# ============================================================
# 2. 一票否决
# ============================================================

class TestVeto:
    def test_veto_triggered(self):
        hits = [_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高")]
        assert check_veto(hits) is True

    def test_no_veto(self):
        hits = [_mock_hit("R1", 70, "高"), _mock_hit("R2", 80, "高")]
        assert check_veto(hits) is False

    def test_empty_no_veto(self):
        assert check_veto([]) is False


# ============================================================
# 3. 评分 → 等级/决策映射 (按 event_type 拆阈值)
# ============================================================

class TestScoreMapping:
    def test_level_low(self):
        assert _score_to_level(10, "通话") == "低"

    def test_level_high(self):
        assert _score_to_level(70, "通话") == "高"

    def test_level_extreme(self):
        assert _score_to_level(95, "通话") == "极高"

    def test_decision_pass(self):
        assert _score_to_decision(10, "通话") == "通过"

    def test_decision_halt(self):
        assert _score_to_decision(95, "通话") == "关停号码"

    def test_intl_call_stricter(self):
        """国际来电阈值更严: 40 分对通话是'中', 对国际来电是'低'."""
        # 通话 pass=35, 国际来电 pass=40
        assert _score_to_level(37, "通话") == "中"
        assert _score_to_level(37, "国际来电") == "低"


# ============================================================
# 4. ML 概率 → 风险分 (sigmoid 校准)
# ============================================================

class TestMlCalibration:
    def test_zero_prob(self):
        assert _ml_prob_to_risk_score(0.0) == 0

    def test_full_prob(self):
        assert _ml_prob_to_risk_score(1.0) == 100

    def test_mid_prob(self):
        """0.5 → ~78 (k=3)."""
        score = _ml_prob_to_risk_score(0.5)
        assert 75 <= score <= 80

    def test_monotonic(self):
        """概率越大, 校准分越高 (单调递增)."""
        scores = [_ml_prob_to_risk_score(p) for p in [0.1, 0.3, 0.5, 0.7, 0.9]]
        assert scores == sorted(scores)


# ============================================================
# 5. _calculate_decision 双轨融合 + 一票否决双保险
# ============================================================

class TestCalculateDecision:
    def test_no_ml_pure_rule(self):
        """ML 未加载 → 纯规则评分."""
        # patch decision 模块里的 is_model_loaded (from import 绑定在 decision 上)
        from app.engine import decision
        orig_loaded = decision.is_model_loaded
        decision.is_model_loaded = lambda: False
        try:
            hits = [_mock_hit("R1", 70, "高")]
            fs, lv, dc, ml_s, ml_dc = _calculate_decision(hits, {}, "通话")
            assert fs == 70
            assert ml_s == 0.0
            assert ml_dc == "通过"
        finally:
            decision.is_model_loaded = orig_loaded

    def test_veto_overrides_ml(self):
        """一票否决: ML 给低分也强制关停 (双保险)."""
        from app.engine import decision
        # mock ML 返回低风险
        ml_res = SimpleNamespace(score=0.05, decision="通过", is_loaded=True)
        orig_predict = decision.predict
        orig_loaded = decision.is_model_loaded
        decision.predict = lambda f: ml_res
        decision.is_model_loaded = lambda: True
        try:
            hits = [_mock_hit("R002", 95, "极高")]
            fs, lv, dc, ml_s, ml_dc = _calculate_decision(hits, {}, "通话")
            assert dc == "关停号码"
            assert lv == "极高"
            assert fs >= 90  # RISK_VETO_MIN_SCORE
        finally:
            decision.predict = orig_predict
            decision.is_model_loaded = orig_loaded

    def test_ml_fusion_no_veto(self):
        """无否决时, 双轨融合 (加权平均)."""
        from app.engine import decision
        ml_res = SimpleNamespace(score=0.5, decision="人工审核", is_loaded=True)
        orig_predict = decision.predict
        orig_loaded = decision.is_model_loaded
        decision.predict = lambda f: ml_res
        decision.is_model_loaded = lambda: True
        try:
            hits = [_mock_hit("R1", 70, "高")]
            fs, lv, dc, _, _ = _calculate_decision(hits, {}, "通话")
            # rule=70, ml 校准 ≈ 78, 融合 = 0.5*70 + 0.5*78 = 74
            assert 70 <= fs <= 80
        finally:
            decision.predict = orig_predict
            decision.is_model_loaded = orig_loaded
