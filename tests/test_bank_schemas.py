"""银行信贷风控 - API 契约测试 (RED 基线).

期望:
  4 个银行事件 (贷款申请/放款/还款/客户投诉)
  6 个规则分类 (欺诈风险/信用风险/反洗钱/账户风险/贷后风险/合规风险)
  黑名单 4 类 (客户/手机号/地址/设备)
"""
import pytest
from pydantic import ValidationError

from app.schemas import (
    BlacklistCreate,
    RiskCheckRequest,
    RuleCreate,
    UserProfileResponse,
)

BANK_EVENTS = ["贷款申请", "放款", "还款", "客户投诉"]
RULE_CATEGORIES = ["欺诈风险", "信用风险", "反洗钱", "账户风险", "贷后风险", "合规风险"]
BLACKLIST_TYPES = ["客户", "手机号", "地址", "设备"]


class TestBankRiskCheckEvents:
    def test_all_4_bank_events(self):
        for et in BANK_EVENTS:
            req = RiskCheckRequest(event_type=et, source_id="x", user_id="u")
            assert req.event_type == et

    def test_ecom_event_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            RiskCheckRequest(event_type="下单", source_id="x", user_id="u")
        assert "event_type" in str(exc_info.value)


class TestBankRuleCategories:
    def test_all_6_bank_categories(self):
        for cat in RULE_CATEGORIES:
            rule = RuleCreate(
                rule_id=f"R_{cat}", rule_name=cat, rule_category=cat,
                event_type="贷款申请", rule_condition={"field": "x", "op": ">", "value": 1},
                risk_level="高", risk_score=70, action="人工审核",
            )
            assert rule.rule_category == cat

    def test_ecom_category_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            RuleCreate(
                rule_id="R1", rule_name="t", rule_category="订单欺诈",
                event_type="贷款申请", rule_condition={"field": "x", "op": ">", "value": 1},
                risk_level="高", risk_score=70, action="人工审核",
            )
        assert "rule_category" in str(exc_info.value)

    def test_bank_event_in_rule(self):
        rule = RuleCreate(
            rule_id="R2", rule_name="t", rule_category="信用风险",
            event_type="放款", rule_condition={"field": "x", "op": ">", "value": 1},
            risk_level="中", risk_score=50, action="标记",
        )
        assert rule.event_type == "放款"


class TestBankBlacklistTypes:
    def test_all_4_bank_types(self):
        for bt in BLACKLIST_TYPES:
            bl = BlacklistCreate(blacklist_type=bt, blacklist_value="v_1")
            assert bl.blacklist_type == bt

    def test_ecom_type_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            BlacklistCreate(blacklist_type="用户", blacklist_value="u1")
        assert "blacklist_type" in str(exc_info.value)


class TestBankUserProfile:
    def test_bank_profile_fields_exist(self):
        """画像响应包含银行字段 (贷款/逾期/投诉)."""
        fields = set(UserProfileResponse.model_fields.keys())
        assert "total_loans" in fields
        assert "overdue_count" in fields
        assert "overdue_rate" in fields
        assert "avg_loan_amount" in fields
        assert "contact_count" in fields