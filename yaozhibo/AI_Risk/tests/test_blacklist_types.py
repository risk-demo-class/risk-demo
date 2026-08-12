"""教育身份与设备名单的前置短路测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas import RiskCheckRequest
from app.service import event as event_module


def _request() -> RiskCheckRequest:
    return RiskCheckRequest(
        event_type="COURSE_PURCHASE", source_id="ORD-1", user_id="U-1", event_data={},
    )


def _db_with_user(user):
    result = MagicMock()
    result.scalar_one.return_value = user
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_user_core_blacklist_has_highest_priority(monkeypatch):
    db = _db_with_user(SimpleNamespace(user_id="U-1", student_id="S-1", id_card_hash="I-1", device_id="D-1"))
    core = AsyncMock(side_effect=lambda _db, kind, value: kind == "用户")
    extra = AsyncMock(return_value=False)
    monkeypatch.setattr(event_module, "_check_core_blacklist", core)
    monkeypatch.setattr(event_module, "_check_extra_blacklist", extra)
    assert await event_module._check_all_blacklists(db, "U-1") == "用户"
    extra.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_id_extra_blacklist(monkeypatch):
    db = _db_with_user(SimpleNamespace(user_id="U-1", student_id="S-1", id_card_hash="I-1", device_id="D-1"))
    monkeypatch.setattr(event_module, "_check_core_blacklist", AsyncMock(return_value=False))
    monkeypatch.setattr(
        event_module,
        "_check_extra_blacklist",
        AsyncMock(side_effect=lambda _db, kind, value: kind == "student_id" and value == "S-1"),
    )
    assert await event_module._check_all_blacklists(db, "U-1") == "学号"


@pytest.mark.asyncio
async def test_no_blacklist_hit(monkeypatch):
    db = _db_with_user(SimpleNamespace(user_id="U-1", student_id=None, id_card_hash=None, device_id=None))
    monkeypatch.setattr(event_module, "_check_core_blacklist", AsyncMock(return_value=False))
    monkeypatch.setattr(event_module, "_check_extra_blacklist", AsyncMock(return_value=False))
    assert await event_module._check_all_blacklists(db, "U-1") is None


def test_blacklist_reject_keeps_public_response_contract():
    response = event_module._blacklist_reject(_request(), "设备")
    assert response.final_score == 100
    assert response.risk_level == "极高"
    assert response.decision == "拒绝"
    assert response.blocked_by == "设备"
    assert response.assessment_id == "blacklist_reject"


@pytest.mark.asyncio
async def test_process_event_short_circuits_before_decision(monkeypatch):
    validate = AsyncMock()
    check = AsyncMock(return_value="身份证")
    decision = AsyncMock()
    monkeypatch.setattr(event_module, "validate_risk_check_request", validate)
    monkeypatch.setattr(event_module, "_check_all_blacklists", check)
    monkeypatch.setattr(event_module, "run_risk_check", decision)
    response = await event_module.process_event(MagicMock(), _request())
    assert response.blocked_by == "身份证"
    validate.assert_awaited_once()
    decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_calls_decision_when_clear(monkeypatch):
    expected = object()
    monkeypatch.setattr(event_module, "validate_risk_check_request", AsyncMock())
    monkeypatch.setattr(event_module, "_check_all_blacklists", AsyncMock(return_value=None))
    decision = AsyncMock(return_value=expected)
    monkeypatch.setattr(event_module, "run_risk_check", decision)
    assert await event_module.process_event(MagicMock(), _request()) is expected
    decision.assert_awaited_once()
