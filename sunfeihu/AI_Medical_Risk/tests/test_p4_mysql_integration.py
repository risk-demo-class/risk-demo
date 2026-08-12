import os

import pytest
from fastapi.testclient import TestClient

from run_app import app


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MYSQL_TESTS") != "1",
        reason="设置 RUN_MYSQL_TESTS=1 后才运行真实 MySQL 集成测试",
    ),
]


def _admin_client() -> TestClient:
    client = TestClient(app)
    password = os.getenv("TEST_ADMIN_PASSWORD", "admin")
    response = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text
    return client


def test_password_change_revokes_other_sessions():
    admin = _admin_client()
    username = "p4_session_user"
    initial_password = "session123"
    changed_password = "session456"
    users = admin.get("/api/auth/users").json()
    existing = next((row for row in users if row["username"] == username), None)
    if existing is None:
        created = admin.post("/api/auth/users", json={
            "username": username,
            "password": initial_password,
            "display_name": "会话撤销测试用户",
            "role": "viewer",
        })
        assert created.status_code == 200, created.text
    else:
        reset = admin.post(
            f"/api/auth/users/{existing['user_id']}/reset-password",
            json={"new_password": initial_password},
        )
        assert reset.status_code == 200, reset.text

    client_a = TestClient(app)
    client_b = TestClient(app)
    payload = {"username": username, "password": initial_password}
    assert client_a.post("/api/auth/login", json=payload).status_code == 200
    assert client_b.post("/api/auth/login", json=payload).status_code == 200

    changed = client_a.post("/api/auth/change-password", json={
        "current_password": initial_password,
        "new_password": changed_password,
    })
    assert changed.status_code == 200, changed.text
    assert client_a.get("/api/auth/me").status_code == 200
    stale = client_b.get("/api/auth/me")
    assert stale.status_code == 401
    assert "登录状态已失效" in stale.json()["detail"]


def test_auth_pages_patients_and_assessment_detail():
    client = _admin_client()
    for path in ("/dashboard", "/patients", "/rules", "/cases", "/assessments", "/assistant", "/users"):
        assert client.get(path).status_code == 200
    patients = client.get("/api/medical/patients?page_size=5")
    assert patients.status_code == 200
    assert len(patients.json()) == 5
    assessments = client.get("/api/assessments?page_size=1").json()
    assert assessments
    detail = client.get(f"/api/assessments/{assessments[0]['assessment_id']}")
    assert detail.status_code == 200
    assert len(detail.json()["features"]) == 25


def test_public_registration_creates_active_viewer_session():
    client = TestClient(app)
    payload = {"username": "p4_registered", "password": "register123", "display_name": "注册用户"}
    response = client.post("/api/auth/register", json=payload)
    if response.status_code == 409:
        admin = _admin_client()
        users = admin.get("/api/auth/users").json()
        user_id = next(row["user_id"] for row in users if row["username"] == "p4_registered")
        activated = admin.patch(
            f"/api/auth/users/{user_id}",
            json={"role": "viewer", "is_active": True},
        )
        assert activated.status_code == 200, activated.text
        reset = admin.post(
            f"/api/auth/users/{user_id}/reset-password",
            json={"new_password": "register123"},
        )
        assert reset.status_code == 200, reset.text
        response = client.post("/api/auth/login", json={"username": "p4_registered", "password": "register123"})
    assert response.status_code == 200, response.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "viewer"
    assert me.json()["is_active"] is True


def test_rule_create_soft_delete_and_viewer_permission():
    client = _admin_client()
    client.delete("/api/rules/P4QA001")
    payload = {
        "rule_id": "P4QA001",
        "rule_name": "P4 规则管理验收",
        "rule_category": "通用",
        "event_type": "通用",
        "condition": {"feature": "event_total_amount", "op": ">=", "value": 999999},
        "risk_level": "中",
        "risk_score": 40,
        "action": "标记",
        "description": "自动验收规则",
        "priority": 0,
    }
    created = client.post("/api/rules", json=payload)
    assert created.status_code == 200, created.text
    deleted = client.delete("/api/rules/P4QA001")
    assert deleted.status_code == 200, deleted.text

    user_payload = {
        "username": "p4_viewer",
        "password": "viewer123",
        "display_name": "P4只读用户",
        "role": "viewer",
    }
    created_user = client.post("/api/auth/users", json=user_payload)
    if created_user.status_code == 409:
        users = client.get("/api/auth/users").json()
        user_id = next(row["user_id"] for row in users if row["username"] == "p4_viewer")
        client.patch(f"/api/auth/users/{user_id}", json={"role": "viewer", "is_active": True})
        client.post(f"/api/auth/users/{user_id}/reset-password", json={"new_password": "viewer123"})
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "p4_viewer", "password": "viewer123"}).status_code == 200
    assert client.get("/api/rules").status_code == 200
    assert client.post("/api/rules/MR015/toggle").status_code == 403


def test_case_assignment_and_reopen_lifecycle():
    client = _admin_client()
    cases = client.get("/api/cases?page_size=100").json()
    assignable = next((row for row in cases if row["case_status"] in ("待审核", "审核中")), None)
    assert assignable is not None
    assigned = client.post(f"/api/cases/{assignable['case_id']}/assign", json={
        "reviewer": "admin", "comment": "P4 指定审核验收",
    })
    assert assigned.status_code == 200, assigned.text

    terminal = next((row for row in cases if row["case_status"] in ("已通过", "已拒绝", "已关闭")), None)
    assert terminal is not None
    reopened = client.post(f"/api/cases/{terminal['case_id']}/reopen", json={
        "reviewer": "admin", "reason": "P4 重新审核验收",
    })
    assert reopened.status_code == 200, reopened.text
    restored = client.post(f"/api/cases/{terminal['case_id']}/review", json={
        "case_status": terminal["case_status"], "reviewer": "admin", "review_comment": "验收后恢复原终态",
    })
    assert restored.status_code == 200, restored.text
