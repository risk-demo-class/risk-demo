"""制造业经销商特征聚合查询回归测试。

旧测试覆盖已删除的电商逐特征函数。迁移后仍保护同一性能目标：
14 个经销商特征必须由少量聚合查询一次完成，不能退化为逐订单/逐保修循环。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.feature import USER_FEATURE_KEYS, _safe_ratio, compute_user_features


def _result(*, one=None, scalar=None, scalar_one=None, scalars=None, all_rows=None):
    result = MagicMock()
    if one is not None:
        result.one.return_value = one
    result.scalar.return_value = scalar
    result.scalar_one_or_none.return_value = scalar_one
    result.scalars.return_value.all.return_value = scalars or []
    result.all.return_value = all_rows or []
    return result


def _dealer_db(*, empty: bool = False):
    if empty:
        results = [
            _result(one=(0, 0, 0, 0, 0, 0)),
            _result(one=(0, 0, 0)),
            _result(scalar=0),
            _result(scalar=0),
            _result(scalar_one=None),
            _result(scalar_one=None),
            _result(scalars=[]),
            _result(all_rows=[]),
        ]
    else:
        results = [
            _result(one=(4, 1_200_000, 300_000, 600_000, 3, 2)),
            _result(one=(3, 2, 260_000)),
            _result(scalar=5),
            _result(scalar=2),
            _result(scalar_one=None),
            _result(scalar_one="华东"),
            _result(scalars=["华东", "华南"]),
            _result(all_rows=[SimpleNamespace(expected_region="华东", actual_region="华北")]),
        ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    return db


class TestManufacturingAggregateQueries:
    @pytest.mark.asyncio
    async def test_complete_14_slot_contract_and_order(self):
        features = await compute_user_features(_dealer_db(), "DLR001")
        assert tuple(features) == USER_FEATURE_KEYS
        assert len(features) == 14

    @pytest.mark.asyncio
    async def test_uses_bounded_aggregate_query_count(self):
        db = _dealer_db()
        await compute_user_features(db, "DLR001")
        # purchase aggregate + claim aggregate + device/report/auth + 3 region queries
        assert db.execute.await_count == 8

    @pytest.mark.asyncio
    async def test_manufacturing_aggregates_keep_expected_semantics(self):
        features = await compute_user_features(_dealer_db(), "DLR001")
        assert features["user_total_orders"] == 4.0
        assert features["user_total_amount"] == 1_200_000.0
        assert features["user_avg_order_amount"] == 300_000.0
        assert features["user_postsale_count"] == 3.0
        assert features["user_refund_count"] == 2.0
        assert features["user_refund_rate"] == pytest.approx(2 / 3, abs=0.0001)
        assert features["user_postsale_rate"] == 0.6
        assert features["user_complaint_count"] == 2.0
        assert features["user_address_count"] == 3.0

    @pytest.mark.asyncio
    async def test_new_dealer_has_numeric_zero_history(self):
        features = await compute_user_features(_dealer_db(empty=True), "DLR-NEW")
        assert tuple(features) == USER_FEATURE_KEYS
        assert all(value == 0.0 for value in features.values())

    def test_safe_ratio_guards_zero_denominator(self):
        assert _safe_ratio(10, 0) == 0.0
        assert _safe_ratio(3, 4) == 0.75

    @pytest.mark.asyncio
    async def test_no_query_is_issued_per_historical_row(self):
        db = _dealer_db()
        features = await compute_user_features(db, "DLR001")
        assert db.execute.await_count == 8
        assert all(isinstance(value, float) for value in features.values())
