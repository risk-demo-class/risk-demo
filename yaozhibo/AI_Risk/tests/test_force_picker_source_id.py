"""三类教育事件的来源主键派发测试。"""
from app.models_business import LearningProgress, OrderInfo, RefundRequest
from app.service.validator import _EVENT_SOURCE_VALIDATORS, _source_validator_for


def test_course_purchase_uses_order_id():
    model, field, _, _ = _source_validator_for("COURSE_PURCHASE")
    assert model is OrderInfo
    assert field == "order_id"


def test_refund_uses_refund_id():
    model, field, _, _ = _source_validator_for("REFUND_REQUEST")
    assert model is RefundRequest
    assert field == "refund_id"


def test_learning_activity_uses_progress_id():
    model, field, _, _ = _source_validator_for("LEARNING_ACTIVITY")
    assert model is LearningProgress
    assert field == "progress_id"


def test_dispatch_has_no_legacy_event():
    events = {event for group in _EVENT_SOURCE_VALIDATORS for event in group}
    assert events == {"COURSE_PURCHASE", "REFUND_REQUEST", "LEARNING_ACTIVITY"}
