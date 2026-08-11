"""鉴权测试 (2026-08-11 最小鉴权): 登录 + HMAC Token + require_admin 覆盖."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.dependencies.utils import get_dependant
from fastapi.testclient import TestClient

from app.auth import create_token, require_admin, verify_token
from app.config import settings
from app.routers.agent import agent_router
from app.routers.alert import alert_router
from app.routers.auth import auth_router
from app.routers.blacklist import api_add_blacklist, api_remove_blacklist
from app.routers.case import api_review_case
from app.routers.rule import (
    api_create_rule,
    api_delete_rule,
    api_toggle_rule,
    api_update_rule,
)


@pytest.fixture()
def auth_settings(monkeypatch):
    """登录测试用固定账号密码 + 密钥."""
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-pass-123")
    monkeypatch.setattr(settings, "AUTH_SECRET", "unit-test-secret")


@pytest.fixture()
def client(auth_settings):
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


class TestLogin:
    def test_login_wrong_password_returns_401(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_login_success_returns_token(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "test-pass-123"})
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "admin"
        assert data["expires_in"] == settings.AUTH_TOKEN_TTL_HOURS * 3600
        assert verify_token(data["token"]) == "admin"

    def test_login_disabled_without_admin_password(self, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
        app = FastAPI()
        app.include_router(auth_router)
        r = TestClient(app).post("/api/auth/login", json={"username": "a", "password": "b"})
        assert r.status_code == 503

    def test_me_requires_valid_token(self, client):
        assert client.get("/api/auth/me").status_code == 401
        assert client.get(
            "/api/auth/me", headers={"Authorization": "Bearer abc.def"}
        ).status_code == 401
        token = client.post(
            "/api/auth/login", json={"username": "admin", "password": "test-pass-123"}
        ).json()["token"]
        assert client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 200


class TestToken:
    def test_roundtrip(self, auth_settings):
        token = create_token("admin")
        assert verify_token(token) == "admin"

    def test_expired_token_rejected(self, auth_settings):
        token = create_token("admin", ttl_hours=-1)
        assert verify_token(token) is None

    def test_require_admin_raises_401_without_header(self, auth_settings):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(authorization=None)
        assert exc_info.value.status_code == 401


def _has_require_admin(deps) -> bool:
    for d in deps:
        target = getattr(d, "call", None) or getattr(d, "dependency", None)
        if getattr(target, "__name__", "") == "require_admin":
            return True
    return False


class TestProtectedEndpoints:
    """写接口必须挂 require_admin (防止鉴权遗漏回归)."""

    @pytest.mark.parametrize("fn", [
        api_create_rule,
        api_update_rule,
        api_toggle_rule,
        api_delete_rule,
        api_add_blacklist,
        api_remove_blacklist,
        api_review_case,
    ])
    def test_write_endpoints_require_admin(self, fn):
        dependant = get_dependant(path="", call=fn)
        assert _has_require_admin(dependant.dependencies), f"{fn.__name__} 应挂 require_admin"

    def test_agent_router_requires_admin(self):
        assert _has_require_admin(agent_router.dependencies), "agent_router 应挂 require_admin"

    def test_alert_router_requires_admin(self):
        assert _has_require_admin(alert_router.dependencies), "alert_router 应挂 require_admin"
