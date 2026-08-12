"""
规则语义校验测试 (DB-free)
分值 → 风险等级/动作 自动匹配 + 后端"极高 ⇒ 拒绝"语义校验
"""
import pytest
from fastapi import HTTPException

from app.routers.rule import _validate_rule_risk_combo


# 与 app/config.py 决策引擎阈值一致 (PASS=30 / MARK=60 / REVIEW=80)
def score_to_level_action(score: int) -> tuple[str, str]:
    if score < 30:
        return "低", "通过"
    if score < 60:
        return "中", "标记"
    if score < 80:
        return "高", "人工审核"
    return "极高", "拒绝"


class TestScoreMapping:
    """分值 → 等级/动作 映射 (前端 autoMatchLevelAction 与后端口径一致)."""

    @pytest.mark.parametrize("score,level,action", [
        (0, "低", "通过"),
        (29, "低", "通过"),
        (30, "中", "标记"),
        (59, "中", "标记"),
        (60, "高", "人工审核"),
        (79, "高", "人工审核"),
        (80, "极高", "拒绝"),
        (100, "极高", "拒绝"),
    ])
    def test_score_mapping(self, score, level, action):
        assert score_to_level_action(score) == (level, action)


class TestRiskComboValidation:
    """后端语义校验: 极高 必须配 拒绝."""

    def test_extreme_reject_ok(self):
        # 合法组合不抛异常
        _validate_rule_risk_combo("极高", "拒绝")

    def test_normal_combos_ok(self):
        # 业务自定义组合 (如 R005 80分/高/人工审核) 允许
        _validate_rule_risk_combo("高", "人工审核")
        _validate_rule_risk_combo("中", "标记")
        _validate_rule_risk_combo("低", "通过")

    def test_extreme_with_mark_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_rule_risk_combo("极高", "标记")
        assert exc.value.status_code == 400
        assert "极高" in exc.value.detail

    def test_extreme_with_pass_rejected(self):
        with pytest.raises(HTTPException):
            _validate_rule_risk_combo("极高", "通过")
