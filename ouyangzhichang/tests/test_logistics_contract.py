from app.engine.ml_model import FEATURE_COLUMNS
from app.engine.rule import evaluate_condition
from app.schemas import RiskCheckRequest

def test_logistics_request_contract():
    req=RiskCheckRequest(event_type="寄件下单",source_id="S1",user_id="U1",event_data={})
    assert set(req.model_dump()) == {"event_type","source_id","user_id","event_data"}

def test_feature_contract_is_25_dimensions():
    assert len(FEATURE_COLUMNS)==25
    assert len(set(FEATURE_COLUMNS))==25
    assert FEATURE_COLUMNS[0]=="sender_total_shipments"

def test_dangerous_rule_condition():
    condition={"and":[{"field":"shipment_declaration_mismatch","op":"==","value":1},{"field":"shipment_dangerous_flag","op":"==","value":1}]}
    assert evaluate_condition(condition,{"shipment_declaration_mismatch":1,"shipment_dangerous_flag":1})
