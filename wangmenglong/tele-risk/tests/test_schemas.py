"""
Pydantic schema 测试 (无需 DB): 构造 + 序列化 + 字段校验.

覆盖 RiskCheckRequest / RiskCheckResponse / RuleCreate / BlacklistCreate 等.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    AgentChatRequest, AssessmentItem, BlacklistCreate, CaseReviewRequest,
    RiskCheckRequest, RiskCheckResponse, RuleCreate, RuleHitInfo,
)


class TestRiskCheckRequest:
    def test_valid(self):
        req = RiskCheckRequest(
            event_type="通话", source_id="cdr_001", msisdn="13800000001",
        )
        assert req.msisdn == "13800000001"
        assert req.event_data is None

    def test_invalid_event_type(self):
        """event_type 只能是 5 种电信事件 + 通用 (Literal 校验)."""
        with pytest.raises(ValidationError):
            RiskCheckRequest(event_type="下单", source_id="x", msisdn="13800000001")

    def test_with_event_data(self):
        req = RiskCheckRequest(
            event_type="国际来电", source_id="cdr_002", msisdn="13800000001",
            event_data={"called_no": "13900000000", "duration": 5},
        )
        assert req.event_data["duration"] == 5


class TestRiskCheckResponse:
    def test_full_response(self):
        hits = [RuleHitInfo(
            rule_id="R001", rule_name="GOIP", rule_category="通话欺诈",
            risk_level="高", risk_score=70, action="人工审核", description="test",
        )]
        resp = RiskCheckResponse(
            assessment_id="ast_1", event_id="evt_1", msisdn="13800000001",
            final_score=70, risk_level="高", decision="人工审核",
            rule_count=1, triggered_rules=hits, features={"cdr_out_count_1h": 25},
            create_time=datetime.now(), ml_score=0.82, ml_decision="人工审核",
        )
        assert resp.final_score == 70
        assert resp.triggered_rules[0].rule_id == "R001"
        assert resp.ml_score == 0.82

    def test_blacklist_reject_response(self):
        """撞黑响应: blocked_by 非空, ml_score=None."""
        resp = RiskCheckResponse(
            assessment_id="blacklist_reject", event_id="blacklist_reject",
            msisdn="13800000001", final_score=100, risk_level="极高",
            decision="关停号码", rule_count=0, triggered_rules=[], features={},
            create_time=datetime.now(), blocked_by="号卡",
            message="撞黑名单: 号卡",
        )
        assert resp.blocked_by == "号卡"
        assert resp.ml_score is None


class TestRuleCreate:
    def test_valid(self):
        rule = RuleCreate(
            rule_id="R099", rule_name="测试规则", rule_category="通话欺诈",
            event_type="通话", rule_condition={"field": "x", "op": ">", "value": 1},
            risk_level="高", risk_score=70, action="人工审核",
        )
        assert rule.priority == 50  # 默认值

    def test_invalid_score_range(self):
        """risk_score 必须 0-100."""
        with pytest.raises(ValidationError):
            RuleCreate(
                rule_id="R099", rule_name="x", rule_category="通话欺诈",
                rule_condition={}, risk_level="高", risk_score=150, action="人工审核",
            )

    def test_invalid_category(self):
        """rule_category 只能是 6 种电信类别."""
        with pytest.raises(ValidationError):
            RuleCreate(
                rule_id="R099", rule_name="x", rule_category="订单欺诈",
                rule_condition={}, risk_level="高", risk_score=70, action="人工审核",
            )


class TestBlacklistCreate:
    def test_valid(self):
        bl = BlacklistCreate(blacklist_type="号卡", blacklist_value="13800000001", reason="GOIP")
        assert bl.blacklist_type == "号卡"

    def test_invalid_type(self):
        """黑名单类型: 号卡/客户/设备/渠道 (不是 用户/地址/手机号)."""
        with pytest.raises(ValidationError):
            BlacklistCreate(blacklist_type="用户", blacklist_value="x")


class TestCaseReviewRequest:
    def test_valid(self):
        req = CaseReviewRequest(decision="已关停", reviewer="admin")
        assert req.add_to_blacklist is False  # 默认

    def test_invalid_decision(self):
        """decision 只能是 已通过/已拒绝/已关闭/已关停."""
        with pytest.raises(ValidationError):
            CaseReviewRequest(decision="拒绝", reviewer="admin")


class TestAgentChatRequest:
    def test_with_session(self):
        req = AgentChatRequest(message="你好", session_id="sess_123")
        assert req.session_id == "sess_123"

    def test_without_session(self):
        req = AgentChatRequest(message="你好")
        assert req.session_id is None


class TestAssessmentItem:
    def test_serialization(self):
        item = AssessmentItem(
            assessment_id="ast_1", event_id="evt_1", msisdn="13800000001",
            event_type="通话", final_score=70, risk_level="高", decision="人工审核",
            rule_count=1, create_time=datetime.now(),
        )
        d = item.model_dump()
        assert d["msisdn"] == "13800000001"
        assert "ml_score" in d  # Optional 字段也在 dump 里
