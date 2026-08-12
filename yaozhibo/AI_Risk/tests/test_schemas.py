"""Pydantic公共契约的无数据库测试。"""
import pytest
from pydantic import ValidationError

from app.schemas import AgentChatRequest, CaseReviewRequest, RiskCheckRequest, RuleCreate


class TestRiskCheckRequest:
    def test_three_education_events_are_valid(self):
        for event_type in ("COURSE_PURCHASE", "REFUND_REQUEST", "LEARNING_ACTIVITY"):
            request = RiskCheckRequest(
                event_type=event_type,
                source_id="SOURCE-1",
                user_id="USER-1",
                event_data={"channel": "web"},
            )
            assert request.event_type == event_type
            assert request.event_data == {"channel": "web"}

    def test_old_domain_event_is_rejected(self):
        with pytest.raises(ValidationError):
            RiskCheckRequest(event_type="下单", source_id="O-1", user_id="U-1")

    def test_request_has_only_four_public_fields(self):
        assert set(RiskCheckRequest.model_fields) == {
            "event_type", "source_id", "user_id", "event_data",
        }

    def test_missing_source_id_is_rejected(self):
        with pytest.raises(ValidationError):
            RiskCheckRequest(event_type="COURSE_PURCHASE", user_id="U-1")


class TestCaseReviewRequest:
    def test_valid_approval(self):
        request = CaseReviewRequest(decision="已通过", reviewer="teacher")
        assert request.decision == "已通过"
        assert request.add_to_blacklist is False

    def test_invalid_decision(self):
        with pytest.raises(ValidationError):
            CaseReviewRequest(decision="已删除", reviewer="teacher")


class TestRuleCreate:
    def test_valid_education_rule(self):
        rule = RuleCreate(
            rule_id="R_TEST",
            rule_name="测试教育规则",
            rule_category="课程退费",
            event_type="REFUND_REQUEST",
            rule_condition={"field": "refund_study_minutes", "op": "<", "value": 5},
            risk_level="高",
            risk_score=75,
            action="人工审核",
        )
        assert rule.risk_score == 75
        assert rule.priority == 0

    def test_rule_score_out_of_range(self):
        with pytest.raises(ValidationError):
            RuleCreate(
                rule_id="R_BAD", rule_name="越界", rule_category="课程退费",
                event_type="REFUND_REQUEST",
                rule_condition={"field": "refund_amount", "op": ">", "value": 0},
                risk_level="高", risk_score=101, action="人工审核",
            )


def test_agent_chat_request_defaults():
    request = AgentChatRequest(message="查询今天的教育风控情况")
    assert request.session_id is None
