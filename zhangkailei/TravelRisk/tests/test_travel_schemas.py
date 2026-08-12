import pytest
from pydantic import ValidationError

from app.schemas import RiskCheckRequest


@pytest.mark.parametrize("event_type", ["机票预订", "酒店预订", "签证申请", "订单支付"])
def test_all_travel_event_types(event_type):
    req = RiskCheckRequest(event_type=event_type, source_id="SRC1", user_id="TU1")
    assert req.event_type == event_type


def test_ecommerce_event_is_rejected():
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="下单", source_id="O1", user_id="U1")
