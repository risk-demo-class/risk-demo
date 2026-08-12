"""Pydantic schema 单测"""
import pytest
from pydantic import ValidationError

from app.schemas import (
    BlacklistCreate,
    RiskCheckRequest,
    RuleCreate,
)


def test_risk_check_request_valid():
    req = RiskCheckRequest(event_type="下单", source_id="B001", user_id="U001")
    assert req.event_type == "下单"


def test_risk_check_request_invalid_event_type():
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="不存在的事件", source_id="B001", user_id="U001")


def test_risk_check_request_all_event_types():
    for et in ("注册", "下单", "支付", "退改申请", "理赔申请", "投诉"):
        req = RiskCheckRequest(event_type=et, source_id="S001", user_id="U001")
        assert req.event_type == et


def test_rule_create_valid():
    rule = RuleCreate(
        rule_id="R099",
        rule_name="测试规则",
        rule_category="下单欺诈",
        event_type="下单",
        rule_condition={"field": "order_total_amount", "op": ">=", "value": 100},
        risk_level="高",
        risk_score=70,
        action="人工审核",
    )
    assert rule.rule_id == "R099"


def test_rule_create_invalid_category():
    with pytest.raises(ValidationError):
        RuleCreate(
            rule_id="R099", rule_name="x", rule_category="不存在的分类",
            event_type="下单", rule_condition={}, risk_level="高",
            risk_score=70, action="人工审核",
        )


def test_rule_create_score_range():
    with pytest.raises(ValidationError):
        RuleCreate(
            rule_id="R099", rule_name="x", rule_category="下单欺诈",
            event_type="下单", rule_condition={}, risk_level="高",
            risk_score=101, action="人工审核",
        )


def test_blacklist_create():
    b = BlacklistCreate(blacklist_type="手机号", blacklist_value="13800000001")
    assert b.blacklist_type == "手机号"
