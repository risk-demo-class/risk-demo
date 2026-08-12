"""
测试 - 制造业特征工程冗余调用优化 (P5)
compute_user_features 内 _feat_user_total_orders 被 2 个派生函数
(avg_order_amount / warranty_rate) 各调 1 次, 冗余.
修复: 预计算 1 次 total_orders, 传给派生函数复用.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_order_amount,
    _feat_user_total_orders,
    _feat_user_warranty_rate,
    compute_user_features,
)


def _row(value):
    return SimpleNamespace(scalar=MagicMock(return_value=value))


class TestPreComputedTotalOrders:
    """2 个派生函数接受 pre-computed total_orders 时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_total_orders_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_orders(*_args, **_kwargs):
            call_log.append("total_orders")
            return 0  # 不该被调

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 100.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", fake_total_orders)
            mp.setattr(feature_module, "_feat_user_total_amount", fake_total_amount)
            result = await _feat_user_avg_order_amount(db, "D001", total_orders=10)
        assert result == 10.0  # 100 / 10
        assert "total_orders" not in call_log
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_warranty_rate_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_orders(*_args, **_kwargs):
            call_log.append("total_orders")
            return 0

        async def fake_warranty_count(*_args, **_kwargs):
            call_log.append("warranty_count")
            return 8

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", fake_total_orders)
            mp.setattr(feature_module, "_feat_user_warranty_count", fake_warranty_count)
            result = await _feat_user_warranty_rate(db, "D001", total_orders=10)
        assert result == 0.8  # 8 / 10
        assert "total_orders" not in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        """不传 total_orders → 正常调 _feat_user_total_orders (向后兼容)"""
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
            result = await _feat_user_avg_order_amount(db, "D001")
        assert result == 40.0  # 200 / 5
        assert "total_orders" in call_log

    @pytest.mark.asyncio
    async def test_zero_total_orders_returns_zero(self):
        """total_orders=0 时, 派生特征都返回 0, 不再查更多 SQL"""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_amount", fake_should_not_call)
            mp.setattr(feature_module, "_feat_user_warranty_count", fake_should_not_call)
            assert await _feat_user_avg_order_amount(db, "D001", total_orders=0) == 0
            assert await _feat_user_warranty_rate(db, "D001", total_orders=0) == 0
        assert call_log == []


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_orders 只算 1 次."""

    @pytest.mark.asyncio
    async def test_total_orders_called_only_once(self):
        call_counts = {"_feat_user_total_orders": 0}

        async def counting_total_orders(*_args, **_kwargs):
            call_counts["_feat_user_total_orders"] += 1
            return 100

        async def fake_independent(*_args, **_kwargs):
            return 0.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", counting_total_orders)
            for fn_name in [
                "_feat_user_orders_30d", "_feat_user_orders_7d",
                "_feat_user_total_amount", "_feat_user_max_order_amount",
                "_feat_user_warranty_count", "_feat_user_repair_count",
                "_feat_user_dealer_contract_expired", "_feat_user_cancel_count",
                "_feat_user_report_count",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)

            db = MagicMock()
            features = await compute_user_features(db, "D001")

        assert call_counts["_feat_user_total_orders"] == 1
        # 12 个用户特征都返回了
        assert len(features) == 12
        assert features["user_total_orders"] == 100
