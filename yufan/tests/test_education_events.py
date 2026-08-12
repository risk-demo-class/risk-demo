"""阶段 6：教育事件 schema、映射与四步入口测试。"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_service
from app.service.validator import _EVENT_SOURCE_VALIDATORS


EDUCATION_EVENTS = ("课程报名", "退费申请", "直播打赏", "学习行为")


def test_risk_request_accepts_only_four_education_events():
    for event_type in EDUCATION_EVENTS:
        request = RiskCheckRequest(event_type=event_type, source_id="SRC001", user_id="U001")
        assert request.event_type == event_type
        assert request.event_data == {}
        assert request.device_id is None

    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="下单", source_id="SRC001", user_id="U001")


def test_each_event_has_the_expected_source_model_and_primary_key():
    actual = {
        event_type: (config[0].__name__, config[1])
        for event_type, config in _EVENT_SOURCE_VALIDATORS.items()
    }
    assert actual == {
        "课程报名": ("OrderInfo", "order_id"),
        "退费申请": ("RefundRequest", "refund_id"),
        "直播打赏": ("LiveReward", "reward_id"),
        "学习行为": ("LearningProgress", "progress_id"),
    }


@pytest.mark.asyncio
async def test_process_event_keeps_four_step_order(monkeypatch):
    calls = []
    request = RiskCheckRequest(event_type="课程报名", source_id="ORD001", user_id="U001")
    expected = RiskCheckResponse(
        assessment_id="AST001",
        event_id="EVT001",
        user_id="U001",
        final_score=0,
        risk_level="低",
        decision="通过",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
    )

    async def validate(db, req):
        calls.append("validate")

    async def enrich(db, req):
        calls.append("enrich")
        return req

    async def blacklist(db, req):
        calls.append("blacklist")
        return None

    async def decision(db, req):
        calls.append("decision")
        return expected

    monkeypatch.setattr(event_service, "validate_risk_check_request", validate)
    monkeypatch.setattr(event_service, "_enrich_request", enrich)
    monkeypatch.setattr(event_service, "_check_all_blacklists", blacklist)
    monkeypatch.setattr(event_service, "run_risk_check", decision)

    result = await event_service.process_event(SimpleNamespace(), request)
    assert result is expected
    assert calls == ["validate", "enrich", "blacklist", "decision"]


@pytest.mark.asyncio
async def test_blacklist_short_circuits_before_decision(monkeypatch):
    request = RiskCheckRequest(event_type="学习行为", source_id="PROG001", user_id="U001")

    async def no_op(db, req):
        return None

    async def enrich(db, req):
        return req

    async def blocked(db, req):
        return "用户"

    async def must_not_run(db, req):
        raise AssertionError("黑名单命中后不应进入决策引擎")

    monkeypatch.setattr(event_service, "validate_risk_check_request", no_op)
    monkeypatch.setattr(event_service, "_enrich_request", enrich)
    monkeypatch.setattr(event_service, "_check_all_blacklists", blocked)
    monkeypatch.setattr(event_service, "run_risk_check", must_not_run)

    result = await event_service.process_event(SimpleNamespace(), request)
    assert result.decision == "拒绝"
    assert result.blocked_by == "用户"
    assert result.final_score == 100
