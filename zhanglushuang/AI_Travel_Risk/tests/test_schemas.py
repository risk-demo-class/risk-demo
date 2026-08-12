"""Schema 校验测试."""

import pytest
from pydantic import ValidationError

from app.schemas import BlacklistCreate, RiskCheckRequest, RuleCreate


def test_risk_check_request_valid():
    req = RiskCheckRequest(
        event_type="下单",
        source_id="ORD1",
        user_id="U1",
        event_data={"total_amount": 1000},
    )
    assert req.source_id == "ORD1"


def test_risk_check_request_invalid_event_type():
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="不存在的类型", source_id="ORD1", user_id="U1")


def test_blacklist_create_valid():
    item = BlacklistCreate(blacklist_type="护照号", blacklist_value="P001", reason="风险")
    assert item.expire_hours is None


def test_rule_create_valid():
    rule = RuleCreate(
        rule_id="R999",
        rule_name="测试规则",
        rule_category="订单欺诈",
        event_type="下单",
        rule_condition={"field": "order_total_amount", "op": ">", "value": 1000},
        risk_level="高",
        risk_score=70,
        action="人工审核",
    )
    assert rule.rule_id == "R999"
