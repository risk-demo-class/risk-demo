"""Goal 2 可重复银行造数和初始化数据数量测试。"""

import re
from pathlib import Path

from scripts.gen_business_data import RISK_PATTERNS, build_business_data

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TABLES = ("bank_card", "bank_transaction", "loan_application", "login_log")


def _insert_values_count(sql: str, table_name: str) -> int:
    match = re.search(
        rf"INSERT INTO `{table_name}`.*?VALUES\s*(.*?)\s*ON DUPLICATE KEY UPDATE",
        sql,
        re.DOTALL | re.IGNORECASE,
    )
    assert match, f"初始化 SQL 缺少 {table_name} 的幂等 INSERT"
    return len(re.findall(r"^\s*\(", match.group(1), re.MULTILINE))


def test_same_seed_produces_identical_data():
    assert build_business_data(count=100, seed=20260811) == build_business_data(
        count=100, seed=20260811
    )


def test_different_seed_changes_generated_data():
    assert build_business_data(count=100, seed=20260811) != build_business_data(
        count=100, seed=20260812
    )


def test_generated_sources_meet_count_and_cover_all_events():
    data = build_business_data(count=100, seed=20260811)
    counts = data["summary"]["events"]
    assert counts == {"绑卡": 25, "转账": 25, "贷款申请": 25, "登录": 25}
    assert sum(counts.values()) == 100
    assert set(data["risk_patterns"]) == set(RISK_PATTERNS)
    assert all(count > 0 for count in data["risk_patterns"].values())


def test_generated_sensitive_values_are_obviously_fictional_or_hashed():
    data = build_business_data(count=100, seed=20260811)
    assert all(row["user_id"].startswith("DEMO_") for row in data["user_info"])
    assert all(len(row["id_card_hash"]) == 64 for row in data["user_info"])
    assert all(len(row["card_no_hash"]) == 64 for row in data["bank_card"])
    assert all(row["ip"].startswith("IP_DEMO_") for row in data["ip_geo_location"])


def test_static_init_data_contains_at_least_one_hundred_source_rows():
    sql = (ROOT / "sql" / "init_business_data.sql").read_text(encoding="utf-8")
    counts = {table: _insert_values_count(sql, table) for table in SOURCE_TABLES}
    assert all(counts[table] > 0 for table in SOURCE_TABLES)
    assert sum(counts.values()) >= 100


def test_static_init_data_is_idempotent_and_contains_risk_patterns():
    sql = (ROOT / "sql" / "init_business_data.sql").read_text(encoding="utf-8")
    assert sql.count("ON DUPLICATE KEY UPDATE") >= 8
    for marker in RISK_PATTERNS:
        assert marker in sql
