from fastapi.testclient import TestClient

from app.schemas import UserRegisterRequest
from app.service.auth import hash_password, verify_password
from run_app import app


def test_password_is_hashed_with_argon2_and_verifies():
    encoded = hash_password("strong-password")
    assert encoded != "strong-password"
    assert encoded.startswith("$argon2")
    assert verify_password("strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_registration_contract_rejects_weak_or_invalid_usernames():
    valid = UserRegisterRequest(username="risk.user", password="secret123", display_name="审核员")
    assert valid.username == "risk.user"


def test_protected_api_returns_json_401_without_session():
    response = TestClient(app).get("/api/rules")
    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"
