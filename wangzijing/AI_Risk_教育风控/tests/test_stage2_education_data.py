"""第二阶段数据层验收测试，不连接真实数据库。"""
import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import settings
from app.database import Base
from app.models import (
    Course,
    DeviceBinding,
    IdentityVerification,
    LearningProgress,
    OrderInfo,
    RefundRequest,
    RiskBlacklist,
    RiskEvent,
    SysUser,
    UserInfo,
)
from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service.validator import (
    _EVENT_SOURCE_VALIDATORS,
    ensure_source_belongs_to_user,
)
from scripts.gen_business_data import build_dataset, render_sql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUSINESS_TABLES = {
    "user_info",
    "course",
    "order_info",
    "learning_progress",
    "refund_request",
    "identity_verification",
    "device_binding",
}
RISK_TABLES = {
    "risk_rule",
    "risk_event",
    "risk_feature",
    "risk_assessment",
    "risk_case",
    "risk_blacklist",
    "risk_user_profile",
    "risk_action_log",
    "risk_alert",
}
SYSTEM_TABLES = {"sys_user"}


def test_seven_business_nine_risk_and_auth_table_are_registered():
    assert set(Base.metadata.tables) == BUSINESS_TABLES | RISK_TABLES | SYSTEM_TABLES
    assert SysUser.__tablename__ == "sys_user"


def test_business_models_have_expected_table_names():
    models = (
        UserInfo,
        Course,
        OrderInfo,
        LearningProgress,
        RefundRequest,
        IdentityVerification,
        DeviceBinding,
    )
    assert {model.__tablename__ for model in models} == BUSINESS_TABLES


def test_industry_enum_values_are_consistent():
    assert settings.EDUCATION_EVENT_TYPES == ("课程报名", "退费申请", "学历认证")
    assert settings.EDUCATION_BLACKLIST_TYPES == ("用户", "学号", "身份证", "设备指纹")
    assert RiskEvent.__table__.c.event_type.type.enums == ["课程报名", "退费申请", "学历认证"]
    assert RiskBlacklist.__table__.c.blacklist_type.type.enums == ["用户", "学号", "身份证", "设备指纹"]


def test_request_models_accept_only_education_values():
    for event_type in settings.EDUCATION_EVENT_TYPES:
        request = RiskCheckRequest(event_type=event_type, source_id="SOURCE001", user_id="EDU001")
        assert request.event_type == event_type
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="下单", source_id="SOURCE001", user_id="EDU001")

    for blacklist_type in settings.EDUCATION_BLACKLIST_TYPES:
        item = BlacklistCreate(blacklist_type=blacklist_type, blacklist_value="HASH_OR_ID")
        assert item.blacklist_type == blacklist_type


def test_event_source_mapping_covers_all_three_events():
    assert set(_EVENT_SOURCE_VALIDATORS) == set(settings.EDUCATION_EVENT_TYPES)
    assert _EVENT_SOURCE_VALIDATORS["课程报名"][:3] == (OrderInfo, "order_id", "user_id")
    assert _EVENT_SOURCE_VALIDATORS["退费申请"][:3] == (RefundRequest, "refund_id", "user_id")
    assert _EVENT_SOURCE_VALIDATORS["学历认证"][:3] == (IdentityVerification, "verify_id", "user_id")


def test_source_ownership_rejects_horizontal_privilege_escalation():
    class _Result:
        def scalar_one_or_none(self):
            return "EDU002"

    class _Database:
        async def execute(self, _statement):
            return _Result()

    request = RiskCheckRequest(
        event_type="课程报名",
        source_id="ORD00001",
        user_id="EDU001",
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ensure_source_belongs_to_user(_Database(), request))
    assert exc_info.value.status_code == 403


def test_dataset_is_deterministic_and_has_more_than_100_rows():
    anchor = datetime.fromisoformat("2026-08-01T12:00:00")
    first = build_dataset(seed=202608, anchor=anchor)
    second = build_dataset(seed=202608, anchor=anchor)
    assert first == second
    assert {table: len(rows) for table, rows in first.items()} == {
        "user_info": 65,
        "course": 20,
        "order_info": 180,
        "learning_progress": 176,
        "refund_request": 20,
        "identity_verification": 68,
        "device_binding": 64,
    }
    assert sum(len(rows) for rows in first.values()) == 593


def test_dataset_contains_all_five_risk_patterns():
    data = build_dataset(seed=202608, anchor=datetime.fromisoformat("2026-08-01T12:00:00"))
    orders = {row["order_id"]: row for row in data["order_info"]}
    progress = {row["order_id"]: row for row in data["learning_progress"]}

    assert any(
        row["refund_amount"] >= 5000 and progress[row["order_id"]]["total_minutes"] == 0
        for row in data["refund_request"]
    )

    refunds_by_user = {}
    for row in data["refund_request"]:
        refunds_by_user[row["user_id"]] = refunds_by_user.get(row["user_id"], 0) + 1
    assert max(refunds_by_user.values()) >= 3

    device_users = {}
    for row in data["device_binding"]:
        device_users.setdefault(row["device_id_hash"], set()).add(row["user_id"])
    assert max(map(len, device_users.values())) >= 4

    failed_by_user = {}
    for row in data["identity_verification"]:
        if row["verify_result"] == "失败":
            failed_by_user[row["user_id"]] = failed_by_user.get(row["user_id"], 0) + 1
    assert max(failed_by_user.values()) >= 3

    assert any(
        order["user_id"].startswith("RISK")
        and order["final_amount"] >= 10000
        and order["create_time"] >= datetime.fromisoformat("2026-07-31T12:00:00")
        for order in orders.values()
    )


def test_sensitive_identifiers_are_hashes_not_plain_values():
    data = build_dataset(seed=202608, anchor=datetime.fromisoformat("2026-08-01T12:00:00"))
    values = []
    for row in data["user_info"]:
        values.extend((row["student_id_hash"], row["id_number_hash"]))
    for row in data["device_binding"]:
        values.extend((row["device_id_hash"], row["ip_hash"]))
    for value in filter(None, values):
        assert len(value) == 64
        int(value, 16)


def test_committed_seed_sql_matches_generator_output():
    data = build_dataset(seed=202608, anchor=datetime.fromisoformat("2026-08-01T12:00:00"))
    committed = (PROJECT_ROOT / "sql" / "init_business_data.sql").read_text(encoding="utf-8")
    assert committed == render_sql(data)


def test_seed_sql_uses_current_mysql_upsert_syntax():
    data = build_dataset(seed=202608, anchor=datetime.fromisoformat("2026-08-01T12:00:00"))
    sql = render_sql(data)
    assert "AS `new_row` ON DUPLICATE KEY UPDATE" in sql
    assert "VALUES(`" not in sql


def test_database_loader_uses_aiomysql_connection_cleanup_api():
    source = (PROJECT_ROOT / "scripts" / "gen_business_data.py").read_text(encoding="utf-8")
    assert "await connection.ensure_closed()" in source
    assert "wait_closed()" not in source
