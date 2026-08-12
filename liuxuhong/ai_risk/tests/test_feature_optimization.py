"""
测试 - 特征工程冗余调用优化 (P5) - 教育版
【P5 优化】_feat_user_total_enrollments 在 compute_user_features 内被
2 个派生函数 (avg_course_amount / refund_rate) 各调 1 次, 冗余.
修复: 预计算 1 次 total_enrollments, 传给 2 个派生函数复用.
验证:
  1. SQL 次数: 1 次 (从 3 次 → 1 次)
  2. 派生特征结果与原版完全一致
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine import feature as feature_module
from app.engine.feature import (
    _feat_user_avg_course_amount,
    _feat_user_refund_rate,
    _feat_user_total_enrollments,
    compute_user_features,
)


def _row(value):
    """构造 SQLAlchemy Row-like, 让 execute() 返回该值."""
    return SimpleNamespace(scalar=MagicMock(return_value=value))


class TestPreComputedTotalEnrollments:
    """2 个派生函数接受 pre-computed total_enrollments 时不再查 SQL."""

    @pytest.mark.asyncio
    async def test_avg_skips_total_query_when_pre_computed(self):
        """传 total_enrollments=10 → 不该调 _feat_user_total_enrollments"""
        db = MagicMock()
        call_log = []

        async def fake_total(*_args, **_kwargs):
            call_log.append("total_enrollments")
            return 0  # 不该被调

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 100.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_enrollments", fake_total)
            mp.setattr(feature_module, "_feat_user_total_amount", fake_total_amount)
            result = await _feat_user_avg_course_amount(db, "u1", total_enrollments=10)
        assert result == 10.0  # 100 / 10
        assert "total_enrollments" not in call_log, "传 total_enrollments 时不该再查"
        assert "total_amount" in call_log

    @pytest.mark.asyncio
    async def test_refund_rate_skips_query_when_pre_computed(self):
        db = MagicMock()
        call_log = []

        async def fake_total(*_args, **_kwargs):
            call_log.append("total_enrollments")
            return 0

        async def fake_refund_count(*_args, **_kwargs):
            call_log.append("refund_count")
            return 5

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_enrollments", fake_total)
            mp.setattr(feature_module, "_feat_user_refund_count", fake_refund_count)
            result = await _feat_user_refund_rate(db, "u1", total_enrollments=10)
        assert result == 0.5  # 5 / 10
        assert "total_enrollments" not in call_log

    @pytest.mark.asyncio
    async def test_avg_falls_back_to_query_when_not_provided(self):
        """不传 total_enrollments → 正常调 _feat_user_total_enrollments (向后兼容)"""
        db = MagicMock()
        call_log = []

        async def fake_total(*_args, **_kwargs):
            call_log.append("total_enrollments")
            return 5

        async def fake_total_amount(*_args, **_kwargs):
            call_log.append("total_amount")
            return 200.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_enrollments", fake_total)
            mp.setattr(feature_module, "_feat_user_total_amount", fake_total_amount)
            result = await _feat_user_avg_course_amount(db, "u1")
        assert result == 40.0  # 200 / 5
        assert "total_enrollments" in call_log

    @pytest.mark.asyncio
    async def test_zero_total_enrollments_returns_zero(self):
        """total_enrollments=0 时, 2 个派生特征都返回 0, 不再查更多 SQL"""
        db = MagicMock()
        call_log = []

        async def fake_should_not_call(*_args, **_kwargs):
            call_log.append("should_not_call")
            return 99

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_amount", fake_should_not_call)
            mp.setattr(feature_module, "_feat_user_refund_count", fake_should_not_call)
            assert await _feat_user_avg_course_amount(db, "u1", total_enrollments=0) == 0
            assert await _feat_user_refund_rate(db, "u1", total_enrollments=0) == 0
        assert call_log == [], f"total_enrollments=0 时不该查更多, 实际调了 {call_log}"


class TestComputeUserFeaturesOptimization:
    """compute_user_features 内部: total_enrollments 只算 1 次."""

    @pytest.mark.asyncio
    async def test_total_enrollments_called_only_once(self):
        """_feat_user_total_enrollments 整个 compute_user_features 流程里只被调 1 次"""
        call_counts = {"_feat_user_total_enrollments": 0}

        async def counting_total(*_args, **_kwargs):
            call_counts["_feat_user_total_enrollments"] += 1
            return 100  # 假设有 100 单

        async def fake_independent(*_args, **_kwargs):
            return 0.0

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(feature_module, "_feat_user_total_enrollments", counting_total)
            for fn_name in [
                "_feat_user_enrollments_30d", "_feat_user_enrollments_7d",
                "_feat_user_total_amount", "_feat_user_max_course_amount",
                "_feat_user_refund_count", "_feat_user_refund_amount",
                "_feat_user_total_study_minutes", "_feat_user_avg_completion_rate",
                "_feat_user_cancel_count", "_feat_user_device_count",
                "_feat_user_course_category_count",
            ]:
                mp.setattr(feature_module, fn_name, fake_independent)

            db = MagicMock()
            features = await compute_user_features(db, "u1")

        assert call_counts["_feat_user_total_enrollments"] == 1, (
            f"_feat_user_total_enrollments 应该是 1 次, 实际 "
            f"{call_counts['_feat_user_total_enrollments']} 次, 优化失败"
        )
        assert len(features) == 14
        assert features["user_total_enrollments"] == 100
