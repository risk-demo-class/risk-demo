from datetime import date, timedelta

from scripts.gen_risk_data_with_dates import build_date_plan


def test_build_date_plan_creates_records_for_each_of_the_last_seven_days():
    today = date(2026, 8, 12)

    plan = build_date_plan(days=7, per_day=2, end_day=today)

    assert len(plan) == 7
    assert {item for item, _ in plan} == {today - timedelta(days=offset) for offset in range(7)}
    assert all(count == 2 for _, count in plan)
