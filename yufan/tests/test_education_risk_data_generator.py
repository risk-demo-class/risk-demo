"""教育评估历史造数脚本的纯函数测试。"""

from datetime import date
import random

import pytest

from scripts.gen_education_risk_data import (
    build_date_range,
    build_parser,
    calculate_daily_quotas,
    random_time_on_day,
)


def test_default_seven_day_range_is_inclusive():
    dates = build_date_range(7, None, "2026-08-11")
    assert dates == [date(2026, 8, day) for day in range(5, 12)]


def test_explicit_date_range_overrides_days():
    dates = build_date_range(99, "2026-08-01", "2026-08-03")
    assert dates == [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]


def test_invalid_range_is_rejected():
    with pytest.raises(ValueError):
        build_date_range(7, "2026-08-12", "2026-08-11")


def test_random_time_stays_inside_target_day():
    target = date(2026, 8, 1)
    generated = random_time_on_day(target, random.Random(1))
    assert generated.date() == target


def test_default_risk_sample_ratio_is_conservative():
    args = build_parser().parse_args([])
    assert args.days == 7
    assert args.per_day == 10
    assert args.positive_ratio == 0.10
    assert args.review_ratio == 0.20
    assert args.preview is False


def test_default_daily_quota_contains_pending_and_rejected_cases():
    assert calculate_daily_quotas(10) == {
        "normal": 7,
        "review": 2,
        "reject": 1,
    }


def test_daily_quota_rejects_invalid_total_ratio():
    with pytest.raises(ValueError):
        calculate_daily_quotas(10, review_ratio=0.8, reject_ratio=0.3)
