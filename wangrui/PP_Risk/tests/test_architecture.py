import inspect

from app.engine.decision import run_risk_check
from app.models_business import BUSINESS_MODELS, BUSINESS_TABLE_COLUMNS
from app.models_risk import RISK_MODELS
from app.service.event import process_event


def test_exact_model_counts() -> None:
    assert len(BUSINESS_MODELS) == 40
    assert len(BUSINESS_TABLE_COLUMNS) == 40
    assert len(RISK_MODELS) == 9


def test_conversation_relationship_keys() -> None:
    assert BUSINESS_TABLE_COLUMNS["interaction"][0] == "interaction_id"
    assert "interaction_id" in BUSINESS_TABLE_COLUMNS["conversation_segment"]
    assert "segment_id" in BUSINESS_TABLE_COLUMNS["message"]


def test_four_step_event_order_is_stable() -> None:
    source = inspect.getsource(process_event)
    markers = (
        "# 1. Validate business entity",
        "# 2. Enrich generic",
        "# 3. Pre-decision blacklist",
        "# 4. Enter the fixed seven-step",
    )
    positions = [source.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_seven_step_decision_order_is_stable() -> None:
    source = inspect.getsource(run_risk_check)
    positions = [source.index(f"# {step}.") for step in range(1, 8)]
    assert positions == sorted(positions)

