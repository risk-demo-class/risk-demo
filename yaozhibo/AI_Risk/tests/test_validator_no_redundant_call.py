"""业务校验只在process_event执行一次，决策引擎不重复校验。"""
from pathlib import Path

from app.service import validator


ROOT = Path(__file__).resolve().parents[1]


def test_validator_public_api_is_kept():
    assert callable(validator.ensure_exists)
    assert callable(validator.ensure_user_exists)
    assert callable(validator.ensure_source_matches_event_type)
    assert callable(validator.ensure_source_belongs_to_user)
    assert callable(validator.validate_risk_check_request)


def test_process_event_calls_validator_before_blacklist_and_decision():
    source = (ROOT / "app" / "service" / "event.py").read_text(encoding="utf-8")
    positions = [
        source.index("validate_risk_check_request(db, request)"),
        source.index("_check_all_blacklists(db, request.user_id)"),
        source.index("run_risk_check(db, request)"),
    ]
    assert positions == sorted(positions)


def test_decision_engine_does_not_repeat_business_validation():
    source = (ROOT / "app" / "engine" / "decision.py").read_text(encoding="utf-8")
    assert "from app.service.validator" not in source
    body = source[source.index("async def run_risk_check"):]
    assert "validate_risk_check_request(" not in body


def test_dispatch_table_covers_exactly_three_events():
    assert len(validator._EVENT_SOURCE_VALIDATORS) == 3
