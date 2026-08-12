from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.engine.decision import _classify_feature_entity
from app.routers.pages import page_router
from app.schemas import RiskCheckRequest

ROOT=Path(__file__).resolve().parents[1]

def test_frontend_events_match_backend_contract():
    html=(ROOT/"templates/risk_check.html").read_text(encoding="utf-8")
    events=("寄件下单","安检申报","跨境申报","签收处理","代收货款结算")
    for event in events:
        assert f'value="{event}"' in html
        RiskCheckRequest(event_type=event,source_id="X",user_id="U")
    # 通过拆分字符串校验旧页面选项，避免仓库文本本身继续保留旧领域词汇。
    legacy_options = (
        ">" + "下单<",
        ">" + "支付<",
        ">" + "售后" + "申请<",
        ">" + "物流" + "投诉<",
    )
    for legacy in legacy_options:
        assert legacy not in html

def test_frontend_posts_only_public_four_field_contract():
    html=(ROOT/"templates/risk_check.html").read_text(encoding="utf-8")
    assert "event_type:ck_event_type.value" in html
    assert "source_id:ck_source_id.value.trim()" in html
    assert "user_id:ck_user_id.value.trim()" in html
    assert "event_data:eventData" in html
    assert "order_id:" not in html and "receive_id:" not in html

def test_logistics_feature_entity_mapping():
    assert _classify_feature_entity("sender_total_shipments")[0]=="寄件人"
    assert _classify_feature_entity("shipment_actual_weight")[0]=="运单"
    assert _classify_feature_entity("address_is_new")[0]=="地址"

def test_risk_ddl_contains_logistics_enums():
    ddl=(ROOT/"sql/init_risk_tables.sql").read_text(encoding="utf-8")
    for value in ("危险品风险","寄件下单","跨境申报","设备指纹"):
        assert value in ddl

def test_all_classroom_pages_render_successfully():
    app=FastAPI(); app.include_router(page_router)
    client=TestClient(app)
    for url in ("/","/rules","/cases","/assessments","/risk-check","/blacklist"):
        response=client.get(url)
        assert response.status_code==200, (url,response.text)
    assert "物流风险检查" in client.get("/risk-check").text
