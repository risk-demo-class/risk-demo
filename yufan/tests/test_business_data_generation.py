"""教育业务造数脚本的完整性和风险样本测试。"""

from datetime import datetime, timedelta
from decimal import Decimal

from scripts.gen_business_data import build_dataset, render_sql


ANCHOR = datetime(2026, 8, 11, 12, 0, 0)


def _dataset():
    return build_dataset(ANCHOR, seed=20260811)


def test_dataset_size_ids_and_foreign_keys():
    dataset = _dataset()
    assert dataset.total_rows >= 500
    assert dataset.event_rows >= 100
    assert len(dataset.tables["order_info"]) >= 100

    primary_keys = {
        "user_info": "user_id",
        "course": "course_id",
        "order_info": "order_id",
        "learning_progress": "progress_id",
        "refund_request": "refund_id",
        "live_reward": "reward_id",
        "blacklist_extra": "entry_id",
    }
    for table, key in primary_keys.items():
        values = [row[key] for row in dataset.tables[table]]
        assert len(values) == len(set(values)), f"{table}.{key} 出现重复"

    users = {row["user_id"] for row in dataset.tables["user_info"]}
    courses = {row["course_id"] for row in dataset.tables["course"]}
    orders = {row["order_id"] for row in dataset.tables["order_info"]}
    for row in dataset.tables["course"]:
        assert row["teacher_id"] in users
    for row in dataset.tables["order_info"]:
        assert row["user_id"] in users
        assert row["course_id"] in courses
    for row in dataset.tables["learning_progress"]:
        assert row["order_id"] in orders
        assert row["user_id"] in users
        assert row["course_id"] in courses
    for row in dataset.tables["refund_request"]:
        assert row["order_id"] in orders
    for row in dataset.tables["live_reward"]:
        assert row["user_id"] in users
        assert row["teacher_id"] in users


def test_three_required_risk_patterns_are_detectable():
    dataset = _dataset()
    users = {row["user_id"]: row for row in dataset.tables["user_info"]}
    orders = dataset.tables["order_info"]
    progress = dataset.tables["learning_progress"]
    refunds = dataset.tables["refund_request"]

    brush_users = [row for row in users.values() if row["user_id"].startswith("RISK_BRUSH_")]
    brush_orders = [row for row in orders if row["user_id"].startswith("RISK_BRUSH_")]
    assert len(brush_users) == 6
    assert {row["device_id"] for row in brush_users} == {"DEV_RISK_BRUSH_SHARED"}
    assert all(ANCHOR - row["register_at"] < timedelta(days=7) for row in brush_users)
    assert len(brush_orders) == 6
    assert {row["course_id"] for row in brush_orders} == {"C001"}

    order_by_id = {row["order_id"]: row for row in orders}
    progress_by_order = {row["order_id"]: row for row in progress}
    for index in range(1, 4):
        user_id = f"RISK_REFUND_{index:03d}"
        user_refunds = [
            row for row in refunds if order_by_id[row["order_id"]]["user_id"] == user_id
        ]
        assert len(user_refunds) >= 3
        assert sum(row["refund_amount"] for row in user_refunds) > Decimal("10000")
        assert all(
            progress_by_order[row["order_id"]]["total_minutes"] < 5
            for row in user_refunds
        )

    proxy_progress = [
        row for row in progress if row["device_id"] == "DEV_RISK_PROXY_SHARED"
    ]
    assert len({row["user_id"] for row in proxy_progress}) >= 5


def test_additional_big_order_live_reward_and_blacklist_patterns():
    dataset = _dataset()
    big_orders = [
        row for row in dataset.tables["order_info"] if row["user_id"] == "RISK_BIG_001"
    ]
    assert len(big_orders) == 4
    assert max(row["order_time"] for row in big_orders) - min(
        row["order_time"] for row in big_orders
    ) < timedelta(hours=1)
    assert sum(row["total_amount"] for row in big_orders) > Decimal("30000")

    risk_reward = next(
        row for row in dataset.tables["live_reward"] if row["reward_id"] == "REWARD_RISK_0001"
    )
    risk_user = next(
        row for row in dataset.tables["user_info"] if row["user_id"] == "RISK_LIVE_001"
    )
    assert risk_reward["reward_amount"] > Decimal("5000")
    assert ANCHOR - risk_user["register_at"] < timedelta(days=30)
    assert risk_reward["guardian_consent_snapshot"] == "待确认"

    blacklist_types = {row["entry_type"] for row in dataset.tables["blacklist_extra"]}
    assert blacklist_types == {"学号", "身份证哈希", "设备指纹", "直播账号"}


def test_sql_generation_is_deterministic_and_idempotent():
    first = render_sql(build_dataset(ANCHOR, seed=20260811))
    second = render_sql(build_dataset(ANCHOR, seed=20260811))
    assert first == second
    assert "AS new\nON DUPLICATE KEY UPDATE" in first
    assert "=new.`" in first
    assert "START TRANSACTION" in first
    assert "COMMIT" in first
    assert "demo-id-card:" not in first
    assert "总行数=" in first
