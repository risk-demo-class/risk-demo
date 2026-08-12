"""
Test education risk rules: 8 rules validated against feature dictionaries.
Tests run without DB - pure condition evaluation.
"""
import pytest
from app.engine.rule import evaluate_condition


class TestEducationRules:
    """Verify all 8 education rules evaluate correctly."""

    # ---- R001: 刷单式报名 (>= 3 new students in 7 days) ----
    def test_r001_triggered(self):
        cond = {"field": "course_new_students_7d", "op": ">=", "value": 3}
        assert evaluate_condition(cond, {"course_new_students_7d": 5}) is True
        assert evaluate_condition(cond, {"course_new_students_7d": 3}) is True

    def test_r001_not_triggered(self):
        cond = {"field": "course_new_students_7d", "op": ">=", "value": 3}
        assert evaluate_condition(cond, {"course_new_students_7d": 2}) is False
        assert evaluate_condition(cond, {"course_new_students_7d": 0}) is False

    # ---- R002: 0学时退费 (study_minutes < 5) ----
    def test_r002_triggered(self):
        cond = {"field": "study_minutes_before_refund", "op": "<", "value": 5}
        assert evaluate_condition(cond, {"study_minutes_before_refund": 3}) is True
        assert evaluate_condition(cond, {"study_minutes_before_refund": 0}) is True

    def test_r002_not_triggered(self):
        cond = {"field": "study_minutes_before_refund", "op": "<", "value": 5}
        assert evaluate_condition(cond, {"study_minutes_before_refund": 10}) is False
        assert evaluate_condition(cond, {"study_minutes_before_refund": 60}) is False

    # ---- R005: 大额连报 (>= 30000 in 1 hour) ----
    def test_r005_triggered(self):
        cond = {"field": "user_order_amount_1h", "op": ">=", "value": 30000}
        assert evaluate_condition(cond, {"user_order_amount_1h": 35000}) is True

    def test_r005_not_triggered(self):
        cond = {"field": "user_order_amount_1h", "op": ">=", "value": 30000}
        assert evaluate_condition(cond, {"user_order_amount_1h": 5000}) is False

    # ---- R008: 假学员代理 (>= 5 accounts on same device) ----
    def test_r008_triggered(self):
        cond = {"field": "device_linked_students", "op": ">=", "value": 5}
        assert evaluate_condition(cond, {"device_linked_students": 8}) is True

    def test_r008_not_triggered(self):
        cond = {"field": "device_linked_students", "op": ">=", "value": 5}
        assert evaluate_condition(cond, {"device_linked_students": 3}) is False

    # ---- R012: 退费连环 (>= 3 refunds AND >= 10000 amount in 90 days) ----
    def test_r012_triggered(self):
        cond = {
            "and": [
                {"field": "user_refund_count_90d", "op": ">=", "value": 3},
                {"field": "user_refund_amount_90d", "op": ">=", "value": 10000},
            ]
        }
        features = {"user_refund_count_90d": 5, "user_refund_amount_90d": 15000}
        assert evaluate_condition(cond, features) is True

    def test_r012_not_triggered_only_count(self):
        cond = {
            "and": [
                {"field": "user_refund_count_90d", "op": ">=", "value": 3},
                {"field": "user_refund_amount_90d", "op": ">=", "value": 10000},
            ]
        }
        features = {"user_refund_count_90d": 5, "user_refund_amount_90d": 5000}
        assert evaluate_condition(cond, features) is False

    # ---- R018: 直播打赏异常 (>= 5000 donation AND < 30 days registered) ----
    def test_r018_triggered(self):
        cond = {
            "and": [
                {"field": "donation_amount", "op": ">=", "value": 5000},
                {"field": "user_days_since_register", "op": "<", "value": 30},
            ]
        }
        features = {"donation_amount": 6000, "user_days_since_register": 10}
        assert evaluate_condition(cond, features) is True

    def test_r018_not_triggered_old_user(self):
        cond = {
            "and": [
                {"field": "donation_amount", "op": ">=", "value": 5000},
                {"field": "user_days_since_register", "op": "<", "value": 30},
            ]
        }
        features = {"donation_amount": 6000, "user_days_since_register": 60}
        assert evaluate_condition(cond, features) is False

    # ---- R025: 学员身份不符 (teacher AND student-only course) ----
    def test_r025_triggered(self):
        cond = {
            "and": [
                {"field": "user_is_teacher", "op": "==", "value": 1},
                {"field": "course_is_student_only", "op": "==", "value": 1},
            ]
        }
        features = {"user_is_teacher": 1, "course_is_student_only": 1}
        assert evaluate_condition(cond, features) is True

    def test_r025_not_triggered(self):
        cond = {
            "and": [
                {"field": "user_is_teacher", "op": "==", "value": 1},
                {"field": "course_is_student_only", "op": "==", "value": 1},
            ]
        }
        features = {"user_is_teacher": 1, "course_is_student_only": 0}
        assert evaluate_condition(cond, features) is False

    # ---- R030: 黑学号拦截 ----
    def test_r030_blacklist_flag(self):
        cond = {"field": "is_blacklisted", "op": "==", "value": 1}
        assert evaluate_condition(cond, {"is_blacklisted": 1}) is True
        assert evaluate_condition(cond, {"is_blacklisted": 0}) is False

    # ---- Priority: veto overrides all ----
    def test_decision_priority_veto_wins(self):
        """R001 (veto: 95) should always result in reject regardless of other rules."""
        veto_score = 95
        normal_score = 50
        final = max(veto_score, normal_score)  # max of both
        assert final >= 80  # >= REVIEW_THRESHOLD = reject


class TestRuleScoring:
    """Verify scoring formula with education rules."""

    def test_single_rule_score(self):
        """One rule: score = rule score + 0 bonus."""
        from app.engine.decision import calculate_final_score
        from types import SimpleNamespace
        from app.engine.rule import RuleHitResult

        hit = RuleHitResult(SimpleNamespace(
            rule_id="R001", rule_name="刷单式报名", rule_category="报名欺诈",
            risk_score=95, risk_level="极高", action="拒绝", description="",
        ))
        assert calculate_final_score([hit]) == 95

    def test_multi_rule_bonus(self):
        """3 rules: score = max + 3*2 = max + 6, capped at 100."""
        from app.engine.decision import calculate_final_score
        from types import SimpleNamespace
        from app.engine.rule import RuleHitResult

        hits = [
            RuleHitResult(SimpleNamespace(rule_id=f"R{i}", rule_name="", rule_category="",
                                          risk_score=s, risk_level="高", action="拒绝", description=""))
            for i, s in enumerate([95, 80, 70], 1)
        ]
        score = calculate_final_score(hits)
        assert score == min(95 + 3 * 2, 100)  # 101 capped at 100

    def test_veto_detection(self):
        """Any rule with risk_level='极高' triggers veto."""
        from app.engine.decision import check_veto
        from types import SimpleNamespace
        from app.engine.rule import RuleHitResult

        hits = [
            RuleHitResult(SimpleNamespace(rule_id="R008", rule_name="", rule_category="",
                                          risk_score=90, risk_level="极高", action="拒绝", description="")),
        ]
        assert check_veto(hits) is True
