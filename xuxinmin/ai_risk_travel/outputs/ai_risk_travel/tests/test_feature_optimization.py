"""
测试 - 旅游特征工程冗余调用优化 (P5)
compute_user_features 预计算 1 次 total_orders, 传给派生特征复用.
"""
from unittest.mock import MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_order_amount,
    _feat_user_refund_rate,
    _feat_user_total_orders,
    compute_user_features,
)


class TestPreComputedTotalOrders:
    """派生函数接受 pre-computed total_orders 时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_total_orders_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_orders(*_args, **_kwargs):
            call_log.append("total_orders")
            return 0

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 100.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", fake_total_orders)
            mp.setattr(feature_module, "_feat_user_total_amount", fake_total_amount)
            result = await _feat_user_avg_order_amount(db, "u1", total_orders=10)
        assert result == 10.0
        assert "total_orders" not in call_log
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_refund_rate_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_orders(*_args, **_kwargs):
            call_log.append("total_orders")
            return 0

        async def fake_refund_count(*_args, **_kwargs):
            call_log.append("refund_count")
            return 5

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", fake_total_orders)
            mp.setattr(feature_module, "_feat_user_refund_count", fake_refund_count)
            result = await _feat_user_refund_rate(db, "u1", total_orders=10)
        assert result == 0.5
        assert "total_orders" not in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        db = MagicMock()
        call_log = []

        async def fake_total_orders(*_args, **_kwargs):
            call_log.append("total_orders")
            return 5

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 200.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", fake_total_orders)
            mp.setattr(feature_module, "_feat_user_total_amount", fake_total_amount)
            result = await _feat_user_avg_order_amount(db, "u1")
        assert result == 40.0
        assert "total_orders" in call_log

    @pytest.mark.asyncio
    async def test_zero_total_orders_returns_zero(self):
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_amount", fake_should_not_call)
            mp.setattr(feature_module, "_feat_user_refund_count", fake_should_not_call)
            assert await _feat_user_avg_order_amount(db, "u1", total_orders=0) == 0
            assert await _feat_user_refund_rate(db, "u1", total_orders=0) == 0
        assert call_log == []


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_orders 只算 1 次, 输出 14 个特征."""

    @pytest.mark.asyncio
    async def test_total_orders_called_only_once(self):
        call_counts = {"_feat_user_total_orders": 0}

        async def counting_total_orders(*_args, **_kwargs):
            call_counts["_feat_user_total_orders"] += 1
            return 100

        async def fake_independent(*_args, **_kwargs):
            return 0.0

        independent_fns = [
            "_feat_user_orders_30d", "_feat_user_orders_7d",
            "_feat_user_total_amount", "_feat_user_max_order_amount",
            "_feat_user_refund_count", "_feat_user_complaint_count",
            "_feat_user_address_count", "_feat_user_visa_reject_count_90d",
            "_feat_user_visa_countries_30d", "_feat_user_real_name_status",
            "_feat_user_account_age_days",
        ]
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", counting_total_orders)
            for fn_name in independent_fns:
                mp.setattr(feature_module, fn_name, fake_independent)
            db = MagicMock()
            features = await compute_user_features(db, "u1")

        assert call_counts["_feat_user_total_orders"] == 1
        assert len(features) == 14
        assert features["user_total_orders"] == 100
        assert set(features.keys()) >= {
            "user_total_orders", "user_orders_30d", "user_orders_7d",
            "user_total_amount", "user_avg_order_amount", "user_max_order_amount",
            "user_refund_count", "user_refund_rate", "user_complaint_count",
            "user_address_count", "user_visa_reject_count_90d",
            "user_visa_countries_30d", "user_real_name_status",
            "user_account_age_days",
        }
