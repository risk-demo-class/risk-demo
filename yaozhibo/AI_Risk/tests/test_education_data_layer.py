"""教育业务数据层的无数据库验收测试。"""
from pathlib import Path

from app.config import BLACKLIST_TYPES, BUSINESS_EVENT_TYPES
from app.models_business import BUSINESS_MODELS
from app.models_risk import (
    RiskActionLog,
    RiskAlert,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskRule,
    RiskUserProfile,
)
from app.service.validator import _EVENT_SOURCE_VALIDATORS
from scripts.gen_business_data import _build_data


ROOT = Path(__file__).resolve().parents[1]


def test_exactly_six_education_business_models():
    assert {model.__tablename__ for model in BUSINESS_MODELS} == {
        "user_info",
        "course",
        "order_info",
        "learning_progress",
        "refund_request",
        "blacklist_extra",
    }


def test_business_ddl_has_exactly_six_tables():
    ddl = (ROOT / "sql" / "init_business_tables.sql").read_text(encoding="utf-8")
    assert ddl.upper().count("CREATE TABLE IF NOT EXISTS") == 6
    for table in ("course", "order_info", "learning_progress", "refund_request"):
        assert f"`{table}`" in ddl
    for stale in ("hospital", "doctor", "prescription", "postsale", "receive_info"):
        assert f"`{stale}`" not in ddl


def test_nine_core_risk_tables_are_preserved():
    risk_models = (
        RiskRule, RiskEvent, RiskFeature, RiskAssessment, RiskCase,
        RiskUserProfile, RiskBlacklist, RiskActionLog, RiskAlert,
    )
    assert {model.__tablename__ for model in risk_models} == {
        "risk_rule",
        "risk_event",
        "risk_feature",
        "risk_assessment",
        "risk_case",
        "risk_user_profile",
        "risk_blacklist",
        "risk_action_log",
        "risk_alert",
    }


def test_education_events_and_dispatch_are_complete():
    dispatched = {event for group in _EVENT_SOURCE_VALIDATORS for event in group}
    assert BUSINESS_EVENT_TYPES == {
        "COURSE_PURCHASE",
        "REFUND_REQUEST",
        "LEARNING_ACTIVITY",
    }
    assert dispatched == BUSINESS_EVENT_TYPES


def test_blacklist_types_cover_education_identity_and_device():
    assert BLACKLIST_TYPES == {"用户", "学号", "身份证", "设备", "直播账号"}


def test_generator_runs_real_pipeline_and_defaults_to_150_events():
    generator = (ROOT / "scripts" / "gen_business_data.py").read_text(encoding="utf-8")
    assert "process_event" in generator
    assert "default=150" in generator
    for marker in ("GEN-U", "GEN-RISK-B", "GEN-RISK-C", "GEN-RISK-D", "GEN-RISK-E", "GEN-RISK-F"):
        assert marker in generator


def test_fixed_scenarios_are_materialized_and_event_volume_is_met():
    users, courses, orders, progresses, refunds, blacklists = _build_data(150, 20260811)
    assert len(orders) + len(progresses) + len(refunds) >= 150
    assert len({user.user_id for user in users}) == len(users)
    assert len({course.course_id for course in courses}) == len(courses)
    assert any(item.refund_id == "GEN-REF-B" and item.study_minutes_before_refund < 5 for item in refunds)
    assert sum(item.user_id == "GEN-RISK-C" for item in refunds) >= 3
    assert sum(item.user_id == "GEN-RISK-E" for item in orders) >= 4
    d_devices = {user.device_id for user in users if user.user_id.startswith("GEN-RISK-D")}
    assert d_devices == {"GEN-DEV-SHARED-D"}
    assert any(item.type == "student_id" and item.value == "GEN-STU-F" for item in blacklists)
    positive_scenarios = (
        sum(item.user_id.startswith("GEN-RISK-D") or item.user_id == "GEN-RISK-E" for item in orders)
        + sum(item.user_id.startswith("GEN-RISK-B") for item in refunds)
    )
    total_events = len(orders) + len(progresses) + len(refunds)
    assert 0.20 <= positive_scenarios / total_events <= 0.30
