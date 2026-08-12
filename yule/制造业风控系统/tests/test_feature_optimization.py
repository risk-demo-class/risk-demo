"""
测试 - 制造业特征工程冗余调用优化 (P5)
【P5 优化 2026-08-07】_feat_user_total_orders 在 compute_user_features 内被
3 个派生函数 (avg / warranty_rate / repair_cost_avg) 各调 1 次, 冗余.
修复: 预计算 1 次 total_orders / warranty_count, 传给派生函数复用.
验证:
  1. SQL 次数: 关键查询只算 1 次
  2. 派生特征结果与原版完全一致
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_order_amount,
    _feat_user_repair_cost_avg,
    _feat_user_total_orders,
    _feat_user_warranty_rate,
    compute_user_features,
)


def _row(value):
    return SimpleNamespace(scalar=MagicMock(return_value=value))


class TestPreComputedValues:
    """3 个派生函数接受 pre-computed 值时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_total_orders_query_when_pre_computed(self):
        """传 total_orders=10 → 不该调 _feat_user_total_orders"""
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
            result = await _feat_user_avg_order_amount(db, "D001", total_orders=10)
        assert result == 10.0  # 100 / 10
        assert "total_orders" not in call_log, "传 total_orders 时不该再查"
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_warranty_rate_skips_query_when_pre_computed(self):
        """传 total_orders=10 → 保修率直接 = warranty_count/10"""
        db = MagicMock()
        call_log = []

        async def fake_total_orders(*_args, **_kwargs):
            call_log.append("total_orders")
            return 0

        async def fake_warranty_count(*_args, **_kwargs):
            call_log.append("warranty_count")
            return 5

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", fake_total_orders)
            mp.setattr(feature_module, "_feat_user_warranty_count", fake_warranty_count)
            result = await _feat_user_warranty_rate(db, "D001", total_orders=10)
        assert result == 0.5  # 5 / 10
        assert "total_orders" not in call_log

    @pytest.mark.asyncio
    async def test_repair_cost_avg_skips_warranty_count_query(self):
        """传 warranty_count=4 → 平均维修费直接 = total/4"""
        db = MagicMock()
        call_log = []

        async def fake_warranty_count(*_args, **_kwargs):
            call_log.append("warranty_count")
            return 0

        async def fake_repair_total(*_args, **_kwargs):
            call_log.append("repair_total")
            return 8000.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_warranty_count", fake_warranty_count)
            mp.setattr(feature_module, "_feat_user_repair_cost_total", fake_repair_total)
            result = await _feat_user_repair_cost_avg(db, "D001", warranty_count=4)
        assert result == 2000.0  # 8000 / 4
        assert "warranty_count" not in call_log

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
    async def test_zero_denominator_returns_zero(self):
        """total_orders=0 / warranty_count=0 时, 派生特征都返回 0, 不再查更多 SQL"""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_amount", fake_should_not_call)
            mp.setattr(feature_module, "_feat_user_warranty_count", fake_should_not_call)
            mp.setattr(feature_module, "_feat_user_repair_cost_total", fake_should_not_call)
            assert await _feat_user_avg_order_amount(db, "D001", total_orders=0) == 0
            assert await _feat_user_warranty_rate(db, "D001", total_orders=0) == 0
            assert await _feat_user_repair_cost_avg(db, "D001", warranty_count=0) == 0
        assert call_log == [], f"分母为 0 时不该查更多, 实际调了 {call_log}"


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_orders / warranty_count 各只算 1 次."""

    @pytest.mark.asyncio
    async def test_key_queries_called_only_once(self):
        """_feat_user_total_orders / _feat_user_warranty_count 整个流程各只调 1 次"""
        call_counts = {"_feat_user_total_orders": 0, "_feat_user_warranty_count": 0}

        async def counting_total_orders(*_args, **_kwargs):
            call_counts["_feat_user_total_orders"] += 1
            return 100

        async def counting_warranty_count(*_args, **_kwargs):
            call_counts["_feat_user_warranty_count"] += 1
            return 40

        async def fake_independent(*_args, **_kwargs):
            return 0.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_orders", counting_total_orders)
            mp.setattr(feature_module, "_feat_user_warranty_count", counting_warranty_count)
            for fn_name in [
                "_feat_user_orders_30d", "_feat_user_orders_7d",
                "_feat_user_total_amount", "_feat_user_max_order_amount",
                "_feat_user_repair_cost_total", "_feat_user_out_warranty_count",
                "_feat_user_cross_report_count", "_feat_user_contract_age_days",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)

            db = MagicMock()
            features = await compute_user_features(db, "D001")

        assert call_counts["_feat_user_total_orders"] == 1, (
            f"_feat_user_total_orders 应只调 1 次, 实际 {call_counts['_feat_user_total_orders']} 次"
        )
        assert call_counts["_feat_user_warranty_count"] == 1, (
            f"_feat_user_warranty_count 应只调 1 次, 实际 {call_counts['_feat_user_warranty_count']} 次"
        )
        # 12 个特征都返回了 (user_repair_cost_avg 已移除, 换 order_cross_report_count)
        assert len(features) == 12
        assert features["user_total_orders"] == 100
        assert features["user_warranty_count"] == 40
