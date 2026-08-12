"""Pydantic schema 银行枚举约束测试"""
import pytest
from pydantic import ValidationError

from app.schemas import BlacklistCreate, RiskCheckRequest, RuleCreate


@pytest.mark.parametrize("evt", ["贷款申请", "放款", "还款", "转账", "登录"])
def test_risk_check_request_banking_events(evt):
    RiskCheckRequest(event_type=evt, source_id="X", user_id="U0001")


def test_risk_check_request_rejects_ecommerce_event():
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="下单", source_id="X", user_id="U0001")


def test_rule_create_banking_enums():
    RuleCreate(
        rule_id="R-T", rule_name="测试", rule_category="信贷欺诈",
        event_type="贷款申请", rule_condition={"field": "order_amount", "op": ">", "value": 1},
        risk_level="高", risk_score=70, action="人工审核",
    )


def test_rule_create_rejects_ecommerce_category():
    with pytest.raises(ValidationError):
        RuleCreate(
            rule_id="R-T", rule_name="测试", rule_category="订单欺诈",
            event_type="下单", rule_condition={},
            risk_level="高", risk_score=70, action="人工审核",
        )


def test_blacklist_create_banking_types():
    for t in ["用户", "身份证号", "手机号", "银行卡号", "设备指纹", "IP", "统一社会信用代码"]:
        BlacklistCreate(blacklist_type=t, blacklist_value="v")


def test_blacklist_create_rejects_ecommerce_type():
    with pytest.raises(ValidationError):
        BlacklistCreate(blacklist_type="地址", blacklist_value="v")
