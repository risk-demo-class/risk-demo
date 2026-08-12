from fastapi.testclient import TestClient

from run_app import app


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["phase"] == "P4"
    assert "loaded" in body["ml_model"]


def test_medical_console_pages_require_login():
    client = TestClient(app)
    for path in ("/dashboard", "/patients", "/risk-check", "/rules", "/cases", "/assessments", "/blacklist", "/assistant", "/system", "/users"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")


def test_login_and_registration_pages_are_public():
    client = TestClient(app)
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200
