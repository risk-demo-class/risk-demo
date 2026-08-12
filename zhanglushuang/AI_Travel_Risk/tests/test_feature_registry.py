"""特征注册表测试."""

from app.engine.feature_registry import FEATURE_COLUMNS, load_feature_config


def test_feature_count():
    features = load_feature_config()
    assert len(FEATURE_COLUMNS) >= 25
    assert len(FEATURE_COLUMNS) == len(features)


def test_feature_names_unique():
    assert len(set(FEATURE_COLUMNS)) == len(FEATURE_COLUMNS)


def test_required_behavior_features():
    for name in [
        "user_orders_7d",
        "user_consecutive_refund_change",
        "device_hotel_account_count",
        "remark_llm_score",
    ]:
        assert name in FEATURE_COLUMNS
