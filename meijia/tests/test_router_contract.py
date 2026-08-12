from collections import Counter

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_routes_are_unique():
    keys = []
    for route in app.routes:
        methods = tuple(sorted(getattr(route, "methods", []) or []))
        keys.append((methods, route.path))
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    assert duplicates == []


def test_expected_api_paths_are_registered():
    expected = {
        "/api/health", "/api/dashboard/overview", "/api/risk/check",
        "/api/rules", "/api/rules/{rule_id}", "/api/rules/{rule_id}/toggle",
        "/api/assessments", "/api/assessments/{assessment_id}",
        "/api/cases", "/api/cases/statistics", "/api/cases/{case_id}",
        "/api/cases/{case_id}/review", "/api/blacklist",
        "/api/blacklist/{entry_id}", "/api/users", "/api/users/{user_id}/profile",
    }
    assert expected <= set(app.openapi()["paths"])


def test_html_pages_are_not_in_openapi():
    documented = set(app.openapi()["paths"])
    for path in ("/", "/risk-check", "/rules", "/assessments", "/cases", "/blacklist", "/users"):
        assert path not in documented
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")


def test_health_and_rule_list():
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/api/rules")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 8
    assert all("enabled" in row for row in data["items"])


def test_risk_check_rejects_missing_context():
    response = client.post(
        "/api/risk/check",
        json={"event_type": "退费申请提交", "user_id": "RISK-STU-001"},
    )
    assert response.status_code == 422
    assert "refund_id" in response.json()["detail"]
    assert response.json()["code"] == "MISSING_EVENT_CONTEXT"


def test_rule_update_validates_condition_and_version():
    current = next(row for row in client.get("/api/rules").json()["items"] if row["rule_id"] == "R002")
    bad = client.put("/api/rules/R002", json={
        "version": current["version"],
        "rule_condition": {"field": "not_a_feature", "op": "<", "value": 5},
    })
    assert bad.status_code == 422
    stale = client.put("/api/rules/R002", json={"version": 999999, "priority": 80})
    assert stale.status_code == 409
