"""
测试 - 特征工程冗余调用优化 (医疗版)
【优化】_feat_user_total_visits / _feat_user_claim_count 在 compute_user_features 内被
派生函数 (avg_claim_amount / cancel_appt_rate) 各调 1 次, 冗余.
修复: 预计算 1 次, 传给派生函数复用.
验证:
  1. SQL 次数: 关键计数特征只查 1 次
  2. 派生特征结果与原版一致
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_claim_amount,
    _feat_user_cancel_appt_rate,
    _feat_user_claim_count,
    _feat_user_total_visits,
    compute_user_features,
)


class TestPreComputedCounts:
    """派生函数接受 pre-computed 计数时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_claim_count_query_when_pre_computed(self):
        """传 claim_count=10 → 不该调 _feat_user_claim_count"""
        db = MagicMock()
        call_log = []

        async def fake_claim_count(*_args, **_kwargs):
            call_log.append("claim_count")
            return 0  # 不该被调

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 100.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_claim_count", fake_claim_count)
            mp.setattr(feature_module, "_feat_user_total_claim_amount", fake_total_amount)
            result = await _feat_user_avg_claim_amount(db, "u1", claim_count=10)
        assert result == 10.0  # 100 / 10
        assert "claim_count" not in call_log, "传 claim_count 时不该再查 _feat_user_claim_count"
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_cancel_rate_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_visits(*_args, **_kwargs):
            call_log.append("total_visits")
            return 0

        async def fake_cancel_count(*_args, **_kwargs):
            call_log.append("cancel_count")
            return 5

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_visits", fake_total_visits)
            mp.setattr(feature_module, "_feat_user_cancel_appt_count", fake_cancel_count)
            result = await _feat_user_cancel_appt_rate(db, "u1", total_visits=10)
        assert result == 0.5  # 5 / 10
        assert "total_visits" not in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        """不传 claim_count → 正常调 _feat_user_claim_count (向后兼容)"""
        db = MagicMock()
        call_log = []

        async def fake_claim_count(*_args, **_kwargs):
            call_log.append("claim_count")
            return 5

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 200.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_claim_count", fake_claim_count)
            mp.setattr(feature_module, "_feat_user_total_claim_amount", fake_total_amount)
            result = await _feat_user_avg_claim_amount(db, "u1")
        assert result == 40.0  # 200 / 5
        assert "claim_count" in call_log  # 向后兼容, 没传就调

    @pytest.mark.asyncio
    async def test_zero_counts_return_zero(self):
        """claim_count=0 / total_visits=0 时, 派生特征返回 0, 不再查更多 SQL"""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_claim_amount", fake_should_not_call)
            mp.setattr(feature_module, "_feat_user_cancel_appt_count", fake_should_not_call)
            assert await _feat_user_avg_claim_amount(db, "u1", claim_count=0) == 0
            assert await _feat_user_cancel_appt_rate(db, "u1", total_visits=0) == 0
        assert call_log == [], f"计数为 0 时不该查更多, 实际调了 {call_log}"


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_visits / claim_count 各只算 1 次."""

    @pytest.mark.asyncio
    async def test_key_counts_called_only_once(self):
        """_feat_user_total_visits / _feat_user_claim_count 全程各只调 1 次"""
        call_counts = {"_feat_user_total_visits": 0, "_feat_user_claim_count": 0}

        async def counting_total_visits(*_args, **_kwargs):
            call_counts["_feat_user_total_visits"] += 1
            return 100

        async def counting_claim_count(*_args, **_kwargs):
            call_counts["_feat_user_claim_count"] += 1
            return 50

        async def fake_independent(*_args, **_kwargs):
            return 0.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_visits", counting_total_visits)
            mp.setattr(feature_module, "_feat_user_claim_count", counting_claim_count)
            for fn_name in [
                "_feat_user_visits_30d", "_feat_user_visits_7d",
                "_feat_user_total_claim_amount", "_feat_user_max_claim_amount",
                "_feat_user_claims_1h_hospitals", "_feat_user_cancel_appt_count",
                "_feat_user_rx_count", "_feat_user_non_self_drug_count",
                "_feat_user_insured_rate", "_feat_user_night_claim_count",
                "_feat_user_cross_hospital_count", "_feat_user_out_region_count",
                "_feat_user_drug_order_count",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)

            db = MagicMock()
            features = await compute_user_features(db, "u1")

        assert call_counts["_feat_user_total_visits"] == 1, (
            f"_feat_user_total_visits 应该是 1 次, 实际 {call_counts['_feat_user_total_visits']} 次"
        )
        assert call_counts["_feat_user_claim_count"] == 1, (
            f"_feat_user_claim_count 应该是 1 次, 实际 {call_counts['_feat_user_claim_count']} 次"
        )
        # 17 个用户特征都返回了
        assert len(features) == 17
        assert features["user_total_visits"] == 100
        assert features["user_claim_count"] == 50