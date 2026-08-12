from fastapi.testclient import TestClient

from app.main import app


def test_v04_pages_and_agent_status_do_not_expose_key() -> None:
    with TestClient(app) as client:
        for path in ("/agent", "/blacklist", "/cases"):
            assert client.get(path).status_code == 200
        status = client.get("/api/agent/status")
        assert status.status_code == 200
        assert "api_key" not in status.text.lower()


def test_risk_trend_windows_and_invalid_window() -> None:
    with TestClient(app) as client:
        for window in ("1h", "6h", "24h", "7d"):
            response = client.get(f"/api/dashboard/risk-trend?window={window}")
            assert response.status_code == 200
            body = response.json()
            assert body["window"] == window
            assert body["points"]
            assert {"time", "transactions", "high_risk", "new_cases"} <= body["points"][0].keys()
        assert client.get("/api/dashboard/risk-trend?window=30d").status_code == 422


def test_blacklist_validation_and_missing_case() -> None:
    with TestClient(app) as client:
        assert client.get("/api/blacklist?active=true").status_code == 200
        assert client.get("/api/cases/DOES-NOT-EXIST").status_code == 404
        invalid = client.post("/api/cases/DOES-NOT-EXIST/review", json={"decision": "已通过", "reviewer": "admin", "review_comment": "test", "add_to_blacklist": True})
        assert invalid.status_code == 422
