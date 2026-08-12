from fastapi.testclient import TestClient


def test_case_list_returns_cases_created_by_high_risk_enrollment():
    from app.main import app

    client = TestClient(app)
    checked = client.post(
        "/api/risk/check",
        json={"event_type": "课程报名", "source_id": "ENR-RISK-001", "user_id": "STU-RISK-01"},
    )
    assert checked.status_code == 200

    response = client.get("/api/cases")

    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert response.json()["items"][0]["event_type"] == "课程报名"


def test_case_page_is_available_from_the_source_style_route():
    from app.main import app

    response = TestClient(app).get("/cases")

    assert response.status_code == 200
    assert "教育风险案件管理" in response.text
    assert 'id="caseTableBody"' in response.text
    assert "/review" in response.text
    assert "仅待办案件" in response.text


def test_case_review_updates_status_and_rejects_terminal_state_changes():
    from app.main import app

    client = TestClient(app)
    client.post(
        "/api/risk/check",
        json={"event_type": "课程报名", "source_id": "ENR-RISK-001", "user_id": "STU-RISK-01"},
    )
    created_case = client.get("/api/cases").json()["items"][0]

    reviewed = client.post(f"/api/cases/{created_case['case_id']}/review", json={"decision": "已通过"})

    assert reviewed.status_code == 200
    assert reviewed.json()["case_status"] == "已通过"
    assert client.get("/api/cases?status=已通过").json()["total"] >= 1

    repeated = client.post(f"/api/cases/{created_case['case_id']}/review", json={"decision": "已拒绝"})

    assert repeated.status_code == 400
