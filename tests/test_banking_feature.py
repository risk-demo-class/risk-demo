"""特征工程纯函数测试 + ML 特征列对齐"""
from datetime import date, datetime

from app.engine.feature import _gap_ratio, _is_night
from app.engine.ml_model import FEATURE_COLUMNS


def test_gap_ratio():
    assert _gap_ratio(10000, 8000) == 0.25
    assert _gap_ratio(8000, 8000) == 0
    assert _gap_ratio(6000, 8000) == 0          # 申报低于核验 → 0
    assert _gap_ratio(10000, 0) == 0            # 核验为 0 → 0, 防除零
    assert _gap_ratio(None, 8000) == 0


def test_is_night():
    assert _is_night(datetime(2026, 8, 11, 3, 0)) == 1
    assert _is_night(datetime(2026, 8, 11, 8, 0)) == 0
    assert _is_night(date(2026, 8, 11)) == 0    # DATE 类型无 hour
    assert _is_night(None) == 0


def test_feature_columns_25():
    assert len(FEATURE_COLUMNS) == 25
    assert any(c.startswith("user_") for c in FEATURE_COLUMNS)
    assert any(c.startswith("order_") for c in FEATURE_COLUMNS)
    assert any(c.startswith("addr_") for c in FEATURE_COLUMNS)
