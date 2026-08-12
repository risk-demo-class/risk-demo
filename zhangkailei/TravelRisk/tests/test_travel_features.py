from app.engine.ml_model import FEATURE_COLUMNS, _features_to_array


def test_feature_contract_has_exactly_25_unique_features():
    assert len(FEATURE_COLUMNS) == 25
    assert len(set(FEATURE_COLUMNS)) == 25


def test_feature_groups_are_complete():
    assert sum(x.startswith("user_") for x in FEATURE_COLUMNS) == 10
    assert sum(x.startswith("order_") for x in FEATURE_COLUMNS) == 10
    assert sum(x.startswith("addr_") for x in FEATURE_COLUMNS) == 5


def test_missing_features_are_zero_filled():
    arr = _features_to_array({"order_total_amount": 50000})
    assert arr.shape == (1, 25)
    assert float(arr[0, FEATURE_COLUMNS.index("order_total_amount")]) == 50000
