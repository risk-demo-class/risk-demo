import json
import logging

from app.logging_config import build_logging_config
from app.observability import (
    JsonLogFormatter,
    classify_outcome,
    pseudonymize,
    sanitize_log_value,
    set_request_context,
    reset_request_context,
)


def test_outcome_classification_separates_policy_validation_and_system_errors() -> None:
    assert classify_outcome("/api/risk/check", 200, "通过") == "BUSINESS_PASS"
    assert classify_outcome("/api/risk/check", 200, "拒绝") == "RISK_POLICY_REJECTED"
    assert classify_outcome("/api/risk/check", 422) == "VALIDATION_ERROR"
    assert classify_outcome("/api/risk/check", 500) == "SYSTEM_ERROR"


def test_sensitive_values_are_redacted_or_pseudonymized() -> None:
    raw_user = "U-VERY-SENSITIVE"
    sanitized = sanitize_log_value(
        {
            "user_id": raw_user,
            "ip": "203.0.113.9",
            "password": "do-not-log",
            "nested": {"card_no_hash": "CARD-HASH"},
        }
    )
    rendered = json.dumps(sanitized)
    assert raw_user not in rendered
    assert "203.0.113.9" not in rendered
    assert "do-not-log" not in rendered
    assert "CARD-HASH" not in rendered
    assert sanitized["user_id"] == pseudonymize(raw_user)


def test_json_formatter_includes_request_context_and_structured_fields() -> None:
    tokens = set_request_context("REQ_test1234", "TRANSFER")
    try:
        record = logging.LogRecord(
            name="bankrisk.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="risk_test_event",
            args=(),
            exc_info=None,
        )
        record.event_data = {"status_code": 200, "user_id": "U_SECRET"}
        payload = json.loads(JsonLogFormatter().format(record))
    finally:
        reset_request_context(tokens)
    assert payload["event"] == "risk_test_event"
    assert payload["request_id"] == "REQ_test1234"
    assert payload["scenario"] == "TRANSFER"
    assert payload["status_code"] == 200
    assert payload["user_id"] != "U_SECRET"


def test_logging_uses_daily_rotation_and_configured_retention() -> None:
    config = build_logging_config()
    for name in ("app_file", "access_file", "decision_file", "alert_file"):
        handler = config["handlers"][name]
        assert handler["class"] == "logging.handlers.TimedRotatingFileHandler"
        assert handler["when"] == "midnight"
        assert handler["backupCount"] >= 1
    assert "alert_file" in config["root"]["handlers"]
    assert config["handlers"]["alert_file"]["level"] == "ERROR"
    assert config["handlers"]["alert_file"]["delay"] is False
