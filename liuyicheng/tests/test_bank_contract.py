import pytest
from pydantic import ValidationError

from app.schemas import BlacklistCreate, RiskCheckRequest, RuleCreate


@pytest.mark.parametrize("event_type", ["信用卡", "贷款", "转账", "登录"])
def test_four_bank_events(event_type):
    request = RiskCheckRequest(
        event_type=event_type, source_id="SRC001", user_id="U001", event_data={},
    )
    assert set(request.model_dump()) == {"event_type", "source_id", "user_id", "event_data"}


def test_old_event_rejected():
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="下单", source_id="O1", user_id="U1", event_data={})


@pytest.mark.parametrize("kind", ["用户", "设备指纹", "IP", "银行卡号", "身份证号"])
def test_bank_blacklist_types(kind):
    assert BlacklistCreate(blacklist_type=kind, blacklist_value="hashed-or-id").blacklist_type == kind


def test_bank_rule_taxonomy():
    rule = RuleCreate(
        rule_id="TEST001", rule_name="测试", rule_category="转账欺诈",
        event_type="转账", rule_condition={"field": "event_amount", "op": ">", "value": 1},
        risk_level="中", risk_score=50, action="标记",
    )
    assert rule.event_type == "转账"
