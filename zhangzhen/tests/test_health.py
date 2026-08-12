from fastapi.testclient import TestClient

from app.api import app


def test_health_reports_registered_tables() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "银行业智能风控系统",
        "environment": "test",
        "business_table_count": 8,
        "risk_table_count": 9,
        "registered_table_count": 17,
    }


def test_healthz_is_available_for_container_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

