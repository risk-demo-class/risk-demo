"""
规则引擎测试 (无需 DB): JSON 条件求值 + 12 条预置规则语法校验.

覆盖:
  - 10 种运算符 (>, >=, <, <=, ==, !=, in, not_in, between, and/or 嵌套)
  - 12 条预置规则的 condition JSON 能被 evaluate_condition 正确求值
  - RuleScoreLevelMismatchError 校验
"""
from types import SimpleNamespace

import pytest

from app.engine.rule import (
    RuleHitResult, RuleScoreLevelMismatchError, evaluate_condition,
    validate_rule_score_level,
)


# ============================================================
# 1. 运算符求值 (10 种)
# ============================================================

class TestOperators:
    """10 种运算符 + and/or 嵌套."""

    def test_gt(self):
        assert evaluate_condition({"field": "x", "op": ">", "value": 5}, {"x": 10}) is True
        assert evaluate_condition({"field": "x", "op": ">", "value": 5}, {"x": 3}) is False

    def test_gte(self):
        assert evaluate_condition({"field": "x", "op": ">=", "value": 5}, {"x": 5}) is True

    def test_lt(self):
        assert evaluate_condition({"field": "x", "op": "<", "value": 5}, {"x": 3}) is True

    def test_lte(self):
        assert evaluate_condition({"field": "x", "op": "<=", "value": 5}, {"x": 5}) is True

    def test_eq(self):
        assert evaluate_condition({"field": "x", "op": "==", "value": 1}, {"x": 1}) is True
        assert evaluate_condition({"field": "x", "op": "==", "value": 1}, {"x": 0}) is False

    def test_neq(self):
        assert evaluate_condition({"field": "x", "op": "!=", "value": 0}, {"x": 5}) is True

    def test_in(self):
        cond = {"field": "x", "op": "in", "value": [1, 2, 3]}
        assert evaluate_condition(cond, {"x": 2}) is True
        assert evaluate_condition(cond, {"x": 5}) is False

    def test_not_in(self):
        cond = {"field": "x", "op": "not_in", "value": [1, 2, 3]}
        assert evaluate_condition(cond, {"x": 5}) is True

    def test_between(self):
        cond = {"field": "x", "op": "between", "value": [10, 20]}
        assert evaluate_condition(cond, {"x": 15}) is True
        assert evaluate_condition(cond, {"x": 10}) is True  # 闭区间
        assert evaluate_condition(cond, {"x": 25}) is False

    def test_and_nested(self):
        cond = {"and": [
            {"field": "a", "op": ">=", "value": 5},
            {"field": "b", "op": ">=", "value": 3},
        ]}
        assert evaluate_condition(cond, {"a": 6, "b": 4}) is True
        assert evaluate_condition(cond, {"a": 6, "b": 2}) is False

    def test_or_nested(self):
        cond = {"or": [
            {"field": "a", "op": ">=", "value": 100},
            {"field": "a", "op": "<", "value": 1},
        ]}
        assert evaluate_condition(cond, {"a": 0}) is True
        assert evaluate_condition(cond, {"a": 50}) is False


# ============================================================
# 2. 边界: 字段缺失 / 未知运算符
# ============================================================

class TestEdgeCases:
    def test_missing_field_returns_false(self):
        """特征不存在 → False (不报错)."""
        assert evaluate_condition({"field": "ghost", "op": ">", "value": 0}, {"real": 1}) is False

    def test_unknown_op_returns_false(self):
        assert evaluate_condition({"field": "x", "op": "regex", "value": ".*"}, {"x": 1}) is False


# ============================================================
# 3. 12 条预置规则条件求值 (用真实 condition JSON)
# ============================================================

# 12 条预置规则的 condition (跟 sql/init_risk_tables.sql 对齐)
PRESET_RULES = [
    ("R001", {"field": "cdr_out_count_1h", "op": ">=", "value": 20}),
    ("R002", {"and": [{"field": "cdr_distinct_cell_1h", "op": "==", "value": 1},
                      {"field": "cdr_out_count_1h", "op": ">=", "value": 10}]}),
    ("R003", {"field": "dev_cards_on_imei", "op": ">=", "value": 5}),
    ("R004", {"field": "cust_card_count", "op": ">=", "value": 5}),
    ("R005", {"field": "cdr_intl_incoming_24h", "op": ">=", "value": 10}),
    ("R006", {"field": "iot_data_burst_ratio", "op": ">=", "value": 10}),
    ("R007", {"field": "channel_open_count_1h", "op": ">=", "value": 8}),
    ("R008", {"and": [{"field": "card_age_days", "op": "<=", "value": 7},
                      {"field": "cdr_out_count_24h", "op": ">=", "value": 50}]}),
    ("R009", {"and": [{"field": "dev_card_imei_mismatch_flag", "op": "==", "value": 1},
                      {"field": "cdr_out_count_1h", "op": ">=", "value": 10}]}),
    ("R010", {"field": "cust_face_verify_passed", "op": "==", "value": 0}),
    ("R011", {"field": "dev_binding_changes_30d", "op": ">=", "value": 3}),
    ("R012", {"and": [{"field": "cdr_short_call_ratio", "op": ">=", "value": 0.8},
                      {"field": "cdr_out_count_24h", "op": ">=", "value": 30}]}),
]


class TestPresetRules:
    """12 条预置规则的 condition JSON 能被正确求值 (命中 + 不命中)."""

    @pytest.mark.parametrize("rule_id,condition", PRESET_RULES)
    def test_rule_condition_valid(self, rule_id, condition):
        """每条规则的 condition 是合法 JSON 条件 (不抛异常)."""
        # 喂空特征, 应返回 False (不命中), 不抛异常
        assert evaluate_condition(condition, {}) is False

    def test_R001_goip_hit(self):
        """R001 GOIP: 1h 主叫 >= 20 命中."""
        cond = PRESET_RULES[0][1]
        assert evaluate_condition(cond, {"cdr_out_count_1h": 25}) is True
        assert evaluate_condition(cond, {"cdr_out_count_1h": 19}) is False

    def test_R003_catpool_hit(self):
        """R003 猫池: 一机多卡 >= 5 命中."""
        cond = PRESET_RULES[2][1]
        assert evaluate_condition(cond, {"dev_cards_on_imei": 5}) is True
        assert evaluate_condition(cond, {"dev_cards_on_imei": 4}) is False

    def test_R008_new_card_high_freq(self):
        """R008 新卡高频: 开卡 <= 7 天 且 24h 主叫 >= 50."""
        cond = PRESET_RULES[7][1]
        assert evaluate_condition(cond, {"card_age_days": 3, "cdr_out_count_24h": 60}) is True
        assert evaluate_condition(cond, {"card_age_days": 30, "cdr_out_count_24h": 60}) is False
        assert evaluate_condition(cond, {"card_age_days": 3, "cdr_out_count_24h": 20}) is False


# ============================================================
# 4. score/level 校验
# ============================================================

class TestScoreLevelValidation:
    def test_valid_combo(self):
        validate_rule_score_level("极高", 95)  # 不抛
        validate_rule_score_level("低", 10)

    def test_mismatch_raises(self):
        with pytest.raises(RuleScoreLevelMismatchError):
            validate_rule_score_level("极高", 50)  # 50 不在 [85,100]

    def test_unknown_level_raises(self):
        with pytest.raises(RuleScoreLevelMismatchError):
            validate_rule_score_level("未知", 50)

    def test_score_out_of_range(self):
        with pytest.raises(RuleScoreLevelMismatchError):
            validate_rule_score_level("低", 150)


# ============================================================
# 5. RuleHitResult
# ============================================================

class TestRuleHitResult:
    def test_to_dict(self):
        mock_rule = SimpleNamespace(
            rule_id="R001", rule_name="GOIP", rule_category="通话欺诈",
            risk_level="高", risk_score=70, action="人工审核", description="test",
        )
        hit = RuleHitResult(mock_rule)
        d = hit.to_dict()
        assert d["rule_id"] == "R001"
        assert d["risk_score"] == 70
        assert len(d) == 7
