from fastapi.testclient import TestClient


def test_dashboard_overview_aggregates_existing_education_risk_records():
    from app.main import app

    client = TestClient(app)
    assert client.post(
        "/api/risk/check",
        json={"event_type": "课程报名", "source_id": "ENR-NORMAL-001", "user_id": "STU-NORMAL-001"},
    ).status_code == 200
    assert client.post(
        "/api/risk/check",
        json={"event_type": "课程报名", "source_id": "ENR-RISK-001", "user_id": "STU-RISK-01"},
    ).status_code == 200

    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["today_assessments"] >= 2
    assert body["pending_cases"] >= 1
    assert isinstance(body["pass_rate"], int)
    assert len(body["trend_7d"]) == 7
    assert any(item["rule_id"] == "EDU-RULE-001" for item in body["top_rules"])


def test_dashboard_page_loads_the_source_style_overview_contract():
    from app.main import app

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert 'id="total-today"' in response.text
    assert "/api/dashboard/overview" in response.text
