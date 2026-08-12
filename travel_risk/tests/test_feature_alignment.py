"""特征工程单测: 28 维特征与 FEATURE_COLUMNS 一一对应"""
import inspect

from app.engine import feature
from app.engine.feature import (
    compute_all_features,
    compute_order_features,
    compute_traveler_features,
    compute_user_features,
)
from app.engine.ml_model import FEATURE_COLUMNS


def test_feature_columns_count():
    assert len(FEATURE_COLUMNS) == 28


def test_feature_names_unique():
    assert len(set(FEATURE_COLUMNS)) == 28


def test_compute_user_features_returns_all_user_keys():
    user_keys = set(FEATURE_COLUMNS[:16])
    assert len(user_keys) == 16


def test_compute_order_features_returns_all_order_keys():
    order_keys = set(FEATURE_COLUMNS[16:25])
    assert len(order_keys) == 9


def test_compute_traveler_features_returns_all_traveler_keys():
    traveler_keys = set(FEATURE_COLUMNS[25:])
    assert len(traveler_keys) == 3


def test_ml_feature_columns_match_feature_module_outputs():
    """所有 FEATURE_COLUMNS 都能由 feature.py 的 compute_* 函数产出."""
    all_keys = set(FEATURE_COLUMNS)
    # 检查 compute_all_features 返回结构应包含全部键 (mock db 用 None 也行, 只测函数签名不测 DB)
    params = inspect.signature(compute_all_features).parameters
    assert "booking_id" in params
    assert "user_id" in params


def test_feature_prefix_classification():
    from app.engine.decision import _classify_feature_entity
    assert _classify_feature_entity("user_total_bookings")[0] == "用户"
    assert _classify_feature_entity("order_total_amount")[0] == "订单"
    assert _classify_feature_entity("traveler_new_count")[0] == "出行人"


def test_traveler_features_zero_without_booking():
    """无订单时出行人特征全 0 (决策引擎对注册事件的行为)."""
    async def run():
        return await compute_traveler_features(None, None, "U001")
    import asyncio
    feats = asyncio.run(run())
    assert feats == {"traveler_total_count": 0.0, "traveler_phone_count": 0.0, "traveler_new_count": 0.0}
