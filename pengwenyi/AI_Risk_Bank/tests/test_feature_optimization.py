"""
测试 - 银行特征工程冗余调用优化
【优化模式】_feat_user_total_txn_count 在 compute_user_features 内预计算 1 次,
传给 _feat_user_avg_txn_amount 复用 (平均交易金额 = 总金额 / 笔数).
验证:
  1. SQL 次数: 笔数只查 1 次
  2. 派生特征结果正确
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_txn_amount,
    _feat_user_total_txn_count,
    compute_user_features,
)


def _row(value):
    """构造 SQLAlchemy Row-like, 让 execute() 返回该值."""
    return SimpleNamespace(scalar=MagicMock(return_value=value))


class TestPreComputedTotalTxnCount:
    """_feat_user_avg_txn_amount 接受 pre-computed total_txn_count 时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_count_query_when_pre_computed(self):
        """传 total_txn_count=10 → 不该调 _feat_user_total_txn_count"""
        db = MagicMock()
        call_log = []

        async def fake_total_count(*_args, **_kwargs):
            call_log.append("total_txn_count")
            return 0  # 不该被调

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 100.0

        # patch 让 _feat_user_total_txn_count / _txn_amount_by_user 走 fake
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_txn_count", fake_total_count)
            mp.setattr(feature_module, "_txn_amount_by_user", fake_total_amount)
            result = await _feat_user_avg_txn_amount(db, "u1", total_txn_count=10)
        assert result == 10.0  # 100 / 10
        assert "total_txn_count" not in call_log, "传 total_txn_count 时不该再查 _feat_user_total_txn_count"
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        """不传 total_txn_count → 正常调 _feat_user_total_txn_count (向后兼容)"""
        db = MagicMock()
        call_log = []

        async def fake_total_count(*_args, **_kwargs):
            call_log.append("total_txn_count")
            return 5

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 200.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_txn_count", fake_total_count)
            mp.setattr(feature_module, "_txn_amount_by_user", fake_total_amount)
            result = await _feat_user_avg_txn_amount(db, "u1")
        assert result == 40.0  # 200 / 5
        assert "total_txn_count" in call_log  # 向后兼容, 没传就调

    @pytest.mark.asyncio
    async def test_zero_total_txn_count_returns_zero(self):
        """total_txn_count=0 时, 平均金额返回 0, 不再查更多 SQL"""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_txn_amount_by_user", fake_should_not_call)
            assert await _feat_user_avg_txn_amount(db, "u1", total_txn_count=0) == 0
        assert call_log == [], f"total_txn_count=0 时不该查金额, 实际调了 {call_log}"


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_txn_count 只算 1 次."""

    @pytest.mark.asyncio
    async def test_total_txn_count_called_only_once(self):
        """_feat_user_total_txn_count 整个 compute_user_features 流程里只被调 1 次"""
        call_counts = {"_feat_user_total_txn_count": 0}

        async def counting_total_count(*_args, **_kwargs):
            call_counts["_feat_user_total_txn_count"] += 1
            return 100  # 假设有 100 笔交易

        # 模拟其他特征函数 (不依赖 total_txn_count)
        async def fake_independent(*_args, **_kwargs):
            return 0.0

        with pytest.MonkeyPatch.context() as mp:
            # 把 _feat_user_total_txn_count 替换成计数版本
            mp.setattr(feature_module, "_feat_user_total_txn_count", counting_total_count)
            # 把其他用户特征都换成 fake (银行版 15 个特征)
            for fn_name in [
                "_feat_user_credit_score", "_feat_user_kyc_level",
                "_feat_user_register_days", "_txn_amount_by_user",
                "_feat_user_avg_txn_amount", "_feat_user_max_txn_amount",
                "_feat_user_total_loan_count", "_feat_user_debt_ratio",
                "_feat_user_monthly_income", "_feat_user_card_count",
                "_feat_user_credit_utilization", "_feat_user_failed_login_7d",
                "_feat_user_device_count", "_feat_user_city_count",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)

            db = MagicMock()
            features = await compute_user_features(db, "u1")

        # 关键断言: _feat_user_total_txn_count 只被调 1 次
        assert call_counts["_feat_user_total_txn_count"] == 1, (
            f"_feat_user_total_txn_count 应该是 1 次, 实际 {call_counts['_feat_user_total_txn_count']} 次, "
            f"优化失败 (avg 特征重算了笔数)"
        )
        # 15 个用户特征都返回了
        assert len(features) == 15
        # user_total_txn_count = 100 (用预计算值)
        assert features["user_total_txn_count"] == 100
