"""阶段 8：教育特征结构与决策引擎兼容性测试。"""

import inspect

from app.engine import feature
from app.engine.ml_model import FEATURE_COLUMNS


def test_three_public_feature_functions_are_kept():
    assert callable(feature.compute_user_features)
    assert callable(feature.compute_order_features)
    assert callable(feature.compute_address_features)


def test_compute_all_features_signature_is_compatible():
    assert list(inspect.signature(feature.compute_all_features).parameters) == [
        "db", "user_id", "order_id", "receive_id",
    ]


def test_feature_columns_remain_14_plus_8_plus_3():
    assert len(FEATURE_COLUMNS) == 25
    assert sum(name.startswith("user_") for name in FEATURE_COLUMNS) == 14
    assert sum(name.startswith("order_") for name in FEATURE_COLUMNS) == 8
    assert sum(name.startswith("addr_") for name in FEATURE_COLUMNS) == 3


def test_feature_module_uses_only_education_models():
    source = inspect.getsource(feature)
    for model_name in (
        "UserInfo", "Course", "OrderInfo", "LearningProgress", "RefundRequest", "LiveReward",
    ):
        assert model_name in source
    for old_model in (
        "Postsale", "ReceiveInfo", "OrderDetail", "SkuInfo", "LogisticsComplaintsRecord",
    ):
        assert old_model not in source


def test_device_features_keep_addr_prefix_for_core_table_compatibility():
    source = inspect.getsource(feature.compute_address_features)
    assert "设备/身份关联特征" in source
    assert all(
        name in source for name in ("addr_total_count", "addr_province_count", "addr_is_new")
    )
