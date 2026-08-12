from fastapi.testclient import TestClient


def test_rule_list_returns_seeded_education_rules():
    from app.main import app

    response = TestClient(app).get("/api/rules")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["items"][0]["rule_id"] == "EDU-RULE-001"


def test_rule_management_page_is_available_from_the_source_style_route():
    from app.main import app

    response = TestClient(app).get("/rules")

    assert response.status_code == 200
    assert "教育风控规则管理" in response.text
    assert 'id="ruleTableBody"' in response.text
