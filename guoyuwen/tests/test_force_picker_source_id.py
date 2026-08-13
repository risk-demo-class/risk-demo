"""四类银行事件 source_id 与 validator 派发表一致性测试。"""

from app.models_business import BankCard, LoanApplication, LoginLog, Transaction
from app.service.validator import _EVENT_SOURCE_VALIDATORS
from scripts.gen_business_data import build_business_data


def test_generated_source_ids_match_validator_models():
    data = build_business_data(count=100, seed=20260811)
    assert all(row["login_id"].startswith("DEMO_") for row in data["login_log"])
    assert all(row["txn_id"].startswith("DEMO_") for row in data["bank_transaction"])
    assert all(row["loan_id"].startswith("DEMO_") for row in data["loan_application"])
    assert all(row["card_id"].startswith("DEMO_") for row in data["bank_card"])


def test_validator_dispatch_uses_exact_source_primary_keys():
    assert {
        event_type: (spec.model, spec.field_name)
        for event_type, spec in _EVENT_SOURCE_VALIDATORS.items()
    } == {
        "登录": (LoginLog, "login_id"),
        "转账": (Transaction, "txn_id"),
        "贷款申请": (LoanApplication, "loan_id"),
        "绑卡": (BankCard, "card_id"),
    }
