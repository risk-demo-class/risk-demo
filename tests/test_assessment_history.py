from fastapi.testclient import TestClient


def test_assessment_list_returns_enrollment_risk_records():
    from app.main import app

    client = TestClient(app)
    client.post(
        "/api/risk/check",
        json={"event_type": "课程报名", "source_id": "ENR-NORMAL-001", "user_id": "STU-NORMAL-001"},
    )

    response = client.get("/api/assessments")

    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert response.json()["items"][0]["event_type"] == "课程报名"


def test_assessment_history_page_uses_the_source_style_route():
    from app.main import app

    response = TestClient(app).get("/assessments")

    assert response.status_code == 200
    assert "教育风险评估历史" in response.text
    assert 'id="assessmentTableBody"' in response.text
