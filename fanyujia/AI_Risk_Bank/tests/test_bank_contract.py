"""银行风控版的核心契约回归测试。"""

import pytest
from pydantic import ValidationError

from app import models_business
from app.engine.ml_model import FEATURE_COLUMNS
from app.schemas import RiskCheckRequest
from app.service.validator import _EVENT_SOURCE_VALIDATORS


def test_bank_request_accepts_transfer_and_rejects_ecommerce_payment():
    request = RiskCheckRequest(
        event_type="转账",
        source_id="TXN000001",
        user_id="U0001",
        event_data={},
    )

    assert request.event_type == "转账"
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="支付", source_id="ORD001", user_id="U0001")


def test_bank_business_layer_exposes_eight_domain_models():
    expected_models = {
        "UserInfo",
        "BankCard",
        "BankTransaction",
        "LoanApplication",
        "LoginLog",
        "DeviceFingerprint",
        "IpGeoLocation",
        "PayeeRelationship",
    }

    assert all(hasattr(models_business, name) for name in expected_models)


def test_bank_event_sources_are_mapped_to_bank_entities():
    assert set(_EVENT_SOURCE_VALIDATORS) == {
        "信用卡交易",
        "转账",
        "贷款申请",
        "登录",
    }


def test_bank_model_uses_exactly_twenty_five_bank_features():
    assert len(FEATURE_COLUMNS) == 25
    assert "user_txn_count_1h" in FEATURE_COLUMNS
    assert "txn_amount" in FEATURE_COLUMNS
    assert "ip_is_tor" in FEATURE_COLUMNS
