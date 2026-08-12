"""四种物流事件的公开 source_id 都统一为运单号。"""
import pytest
from pydantic import ValidationError

from app.config import LOGISTICS_EVENT_TO_CORE
from app.schemas import RiskCheckRequest


@pytest.mark.parametrize(
    ("event_type", "core_event"),
    list(LOGISTICS_EVENT_TO_CORE.items()),
)
def test_four_event_mappings_use_shipment_id(event_type, core_event):
    request = RiskCheckRequest(
        event_type=event_type,
        source_id="SHP0001",
        user_id="U001",
        event_data={},
    )
    assert request.source_id == "SHP0001"
    assert LOGISTICS_EVENT_TO_CORE[request.event_type] == core_event


def test_legacy_event_is_not_public_contract():
    with pytest.raises(ValidationError):
        RiskCheckRequest(event_type="下单", source_id="SHP0001", user_id="U001")
