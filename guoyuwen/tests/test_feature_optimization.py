"""银行特征查询与中性语义回归。"""

import inspect
from datetime import datetime

import pytest

from app.engine.feature import (
    ADDRESS_FEATURE_COLUMNS,
    ORDER_FEATURE_COLUMNS,
    USER_FEATURE_COLUMNS,
    BankEventContext,
    FeatureSourceError,
    compute_order_features,
    compute_user_features,
    load_event_context,
)


class _NoQueryDB:
    async def execute(self, _statement):
        raise AssertionError("绑卡无设备环境的中性维度不应发起额外查询")


@pytest.mark.asyncio
async def test_bind_card_without_environment_uses_explicit_neutral_values():
    context = BankEventContext(
        event_type="绑卡",
        source_id="CARD_DEMO",
        user_id="USR_DEMO",
        event_time=datetime(2026, 8, 12, 10, 0, 0),
    )
    features = await compute_order_features(_NoQueryDB(), context)
    assert list(features) == ORDER_FEATURE_COLUMNS
    assert features == {
        "order_event_amount": 0.0,
        "order_txn_count_1h": 0.0,
        "order_is_night": 0.0,
        "order_new_device_days": 3650.0,
        "order_device_user_count": 1.0,
        "order_payee_card_count_1h": 0.0,
        "order_loan_institution_count_30d": 0.0,
        "order_debt_ratio": 0.0,
    }


@pytest.mark.asyncio
async def test_unknown_event_type_fails_instead_of_filling_zeroes():
    with pytest.raises(FeatureSourceError, match="不支持的银行事件类型"):
        await load_event_context(_NoQueryDB(), "未知事件", "SRC", "USR")


def test_feature_families_remain_14_8_3():
    assert len(USER_FEATURE_COLUMNS) == 14
    assert len(ORDER_FEATURE_COLUMNS) == 8
    assert len(ADDRESS_FEATURE_COLUMNS) == 3


def test_user_history_queries_stop_before_current_event_and_do_not_use_targets():
    source = inspect.getsource(compute_user_features)
    assert "Transaction.txn_at < as_of" in source
    assert "LoginLog.login_at < as_of" in source
    assert "LoanApplication.apply_at < as_of" in source
    for forbidden in ("RiskAssessment", "RiskRule", "final_score", "decision", "label"):
        assert forbidden not in source


def test_transaction_amount_statistics_share_one_aggregate_query():
    source = inspect.getsource(compute_user_features)
    assert "func.sum(Transaction.amount)" in source
    assert "func.avg(Transaction.amount)" in source
    assert "func.max(Transaction.amount)" in source
