"""教育风控版最小接口契约。"""

from app.schemas import RiskCheckRequest
from app.service.validator import _EVENT_SOURCE_VALIDATORS, _get_source_validator


def test_risk_check_accepts_education_event_types():
    """教育版入口应接受三类真实业务事件。"""
    events = ["课程报名", "退费申请", "直播打赏"]
    for event_type in events:
        request = RiskCheckRequest(
            event_type=event_type,
            source_id="demo-source",
            user_id="edu_001",
        )
        assert request.event_type == event_type


def test_every_education_event_has_a_source_validator():
    """三种教育事件都必须能找到对应的业务表校验器。"""
    configured_events = {event for group in _EVENT_SOURCE_VALIDATORS for event in group}
    assert {"课程报名", "退费申请", "直播打赏"} <= configured_events


def test_refund_event_resolves_to_its_business_table():
    """退费申请应解析到 refund_request，而不是按单个字符串错误索引元组字典。"""
    _, field, label = _get_source_validator("退费申请")
    assert field == "refund_id"
    assert label == "退费申请"
