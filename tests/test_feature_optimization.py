"""
测试 - 特征工程冗余调用优化 (P5, 银行版)
【P5 优化】_feat_cust_total_loans 在 compute_user_features 内被
3 个派生函数 (avg_loan_amount / overdue_rate / repay_rate) 各调 1 次, 冗余.
修复: 预计算 1 次 total_loans, 传给 3 个派生函数复用.
验证:
  1. SQL 次数: 1 次 (从 4 次 → 1 次)
  2. 派生特征结果与原版完全一致
"""
from unittest.mock import MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_cust_avg_loan_amount,
    _feat_cust_overdue_rate,
    _feat_cust_repay_rate,
    _feat_cust_total_loans,
    compute_user_features,
)


class TestPreComputedTotalLoans:
    """3 个派生函数接受 pre-computed total_loans 时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_loans(*_a, **_k):
            call_log.append("total_loans")
            return 0  # 不该被调

        async def fake_total_amount(*_a, **_k):
            call_log.append("total_amount")
            return 100.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_cust_total_loans", fake_total_loans)
            mp.setattr(feature_module, "_feat_cust_total_amount", fake_total_amount)
            result = await _feat_cust_avg_loan_amount(db, "c1", total_loans=10)
        assert result == 10.0  # 100 / 10
        assert "total_loans" not in call_log, "传 total_loans 时不该再查 _feat_cust_total_loans"
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_overdue_rate_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_loans(*_a, **_k):
            call_log.append("total_loans")
            return 0

        async def fake_overdue_count(*_a, **_k):
            call_log.append("overdue_count")
            return 4

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_cust_total_loans", fake_total_loans)
            mp.setattr(feature_module, "_feat_cust_overdue_count", fake_overdue_count)
            result = await _feat_cust_overdue_rate(db, "c1", total_loans=10)
        assert result == 0.4  # 4 / 10
        assert "total_loans" not in call_log

    @pytest.mark.asyncio
    async def test_repay_rate_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total_loans(*_a, **_k):
            call_log.append("total_loans")
            return 0

        async def fake_closed(*_a, **_k):
            call_log.append("closed")
            return 6

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_cust_total_loans", fake_total_loans)
            mp.setattr(feature_module, "_count", fake_closed)
            result = await _feat_cust_repay_rate(db, "c1", total_loans=10)
        assert result == 0.6  # 6 / 10
        assert "total_loans" not in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        """不传 total_loans → 正常调 _feat_cust_total_loans (向后兼容)."""
        db = MagicMock()
        call_log = []

        async def fake_total_loans(*_a, **_k):
            call_log.append("total_loans")
            return 5

        async def fake_total_amount(*_a, **_k):
            call_log.append("total_amount")
            return 200.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_cust_total_loans", fake_total_loans)
            mp.setattr(feature_module, "_feat_cust_total_amount", fake_total_amount)
            result = await _feat_cust_avg_loan_amount(db, "c1")
        assert result == 40.0  # 200 / 5
        assert "total_loans" in call_log

    @pytest.mark.asyncio
    async def test_zero_total_loans_returns_zero(self):
        """total_loans=0 时, 3 个派生特征都返回 0, 不再查更多 SQL."""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_a, **_k):
            call_log.append("NOPE")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_cust_total_amount", fake_should_not_call)
            mp.setattr(feature_module, "_feat_cust_overdue_count", fake_should_not_call)
            mp.setattr(feature_module, "_count", fake_should_not_call)
            assert await _feat_cust_avg_loan_amount(db, "c1", total_loans=0) == 0
            assert await _feat_cust_overdue_rate(db, "c1", total_loans=0) == 0
            assert await _feat_cust_repay_rate(db, "c1", total_loans=0) == 0
        assert call_log == [], f"total_loans=0 时不该查更多, 实际调了 {call_log}"


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_loans 只算 1 次."""

    @pytest.mark.asyncio
    async def test_total_loans_called_only_once(self):
        """_feat_cust_total_loans 整个 compute_user_features 流程里只被调 1 次."""
        call_counts = {"_feat_cust_total_loans": 0}

        async def counting_total_loans(*_a, **_k):
            call_counts["_feat_cust_total_loans"] += 1
            return 100  # 假设有 100 笔申请

        async def fake_independent(*_a, **_k):
            return 0.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_cust_total_loans", counting_total_loans)
            for fn_name in [
                "_feat_cust_loans_30d", "_feat_cust_loans_7d",
                "_feat_cust_total_amount", "_feat_cust_max_loan_amount",
                "_feat_cust_overdue_count", "_feat_cust_overdue_amount",
                "_feat_cust_repay_count", "_feat_cust_reject_count",
                "_feat_cust_complaint_count", "_feat_cust_contact_count",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)
            mp.setattr(feature_module, "_count", fake_independent)

            db = MagicMock()
            features = await compute_user_features(db, "c1")

        assert call_counts["_feat_cust_total_loans"] == 1, (
            f"_feat_cust_total_loans 应 1 次, 实际 {call_counts['_feat_cust_total_loans']} 次"
        )
        assert len(features) == 14
        assert features["cust_total_loans"] == 100