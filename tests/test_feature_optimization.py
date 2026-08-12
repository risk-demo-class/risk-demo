"""
测试 - 特征工程冗余调用优化 (P5, 物流版)
【P5 优化】_feat_user_total_parcel_count 在 compute_user_features 内被
派生函数 _feat_user_avg_declared_value 复用, 不各自重查.
验证:
  1. SQL 次数: total_parcels 只查 1 次 (avg_declared_value 复用)
  2. 派生特征结果与原版完全一致
"""
from unittest.mock import MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_declared_value,
    _feat_user_total_parcel_count,
    compute_user_features,
)


class TestPreComputedTotalParcels:
    """派生函数接受 pre-computed total_parcels 时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_total_parcels_query_when_pre_computed(self):
        """传 total_parcels=10 → 不该调 _feat_user_total_parcel_count"""
        db = MagicMock()
        call_log = []

        async def fake_total_parcels(*_args, **_kwargs):
            call_log.append("total_parcels")
            return 0  # 不该被调

        async def fake_sum(*_args, **_kwargs):
            call_log.append("sum_declared")
            return 100.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_parcel_count", fake_total_parcels)
            mp.setattr(feature_module, "_sum", fake_sum)
            result = await _feat_user_avg_declared_value(db, "u1", total_parcels=10)
        assert result == 10.0  # 100 / 10
        assert "total_parcels" not in call_log, "传 total_parcels 时不该再查 _feat_user_total_parcel_count"
        assert "sum_declared" in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        """不传 total_parcels → 正常调 _feat_user_total_parcel_count (向后兼容)"""
        db = MagicMock()
        call_log = []

        async def fake_total_parcels(*_args, **_kwargs):
            call_log.append("total_parcels")
            return 5

        async def fake_sum(*_args, **_kwargs):
            call_log.append("sum_declared")
            return 200.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_parcel_count", fake_total_parcels)
            mp.setattr(feature_module, "_sum", fake_sum)
            result = await _feat_user_avg_declared_value(db, "u1")
        assert result == 40.0  # 200 / 5
        assert "total_parcels" in call_log  # 向后兼容, 没传就调

    @pytest.mark.asyncio
    async def test_zero_total_parcels_returns_zero(self):
        """total_parcels=0 时 avg_declared_value 返回 0, 不再查更多 SQL"""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_sum", fake_should_not_call)
            assert await _feat_user_avg_declared_value(db, "u1", total_parcels=0) == 0
        assert call_log == [], f"total_parcels=0 时不该查更多, 实际调了 {call_log}"


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_parcels 只算 1 次."""

    @pytest.mark.asyncio
    async def test_total_parcels_called_only_once(self):
        """_feat_user_total_parcel_count 整个 compute_user_features 流程里只被调 1 次"""
        call_counts = {"_feat_user_total_parcel_count": 0}

        async def counting_total_parcels(*_args, **_kwargs):
            call_counts["_feat_user_total_parcel_count"] += 1
            return 100  # 假设有 100 票

        # 模拟其他 9 个特征函数 (不依赖 total_parcels)
        async def fake_independent(*_args, **_kwargs):
            return 0.0

        async def fake_sum(*_args, **_kwargs):
            return 1000.0  # avg_declared_value 的 SUM(declared_value)

        with pytest.MonkeyPatch.context() as mp:
            # total_parcels 用计数版本
            mp.setattr(feature_module, "_feat_user_total_parcel_count", counting_total_parcels)
            # 其他用户特征换成 fake
            for fn_name in [
                "_feat_user_account_age_days", "_feat_user_real_name_verified",
                "_feat_user_is_enterprise", "_feat_user_total_parcel_count_30d",
                "_feat_user_total_parcel_count_7d", "_feat_user_distinct_receiver_count",
                "_feat_user_cod_overdue_count", "_feat_user_blacklist_hit_count",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)
            # avg_declared_value 内部走 _sum
            mp.setattr(feature_module, "_sum", fake_sum)

            db = MagicMock()
            features = await compute_user_features(db, "u1")

        # 关键断言: _feat_user_total_parcel_count 只被调 1 次
        assert call_counts["_feat_user_total_parcel_count"] == 1, (
            f"_feat_user_total_parcel_count 应该是 1 次, 实际 {call_counts['_feat_user_total_parcel_count']} 次, "
            f"优化失败 (avg_declared_value 重算了)"
        )
        # 10 个用户特征都返回了
        assert len(features) == 10
        # user_total_parcel_count = 100 (用预计算值)
        assert features["user_total_parcel_count"] == 100
        # avg_declared_value = 1000 / 100 = 10
        assert features["user_avg_declared_value"] == 10.0
