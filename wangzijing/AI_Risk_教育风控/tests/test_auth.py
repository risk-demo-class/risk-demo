"""两角色登录、密码摘要和页面权限的静态回归测试。"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.auth import (
    AuthUser,
    _admin_only_request,
    _role_can_access_path,
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)
from app.schemas import CaseReviewRequest


ROOT = Path(__file__).resolve().parent.parent


def test_password_hash_is_salted_and_verifiable():
    encoded = hash_password("StrongPassword@123", salt=b"0123456789abcdef")
    assert encoded.startswith("pbkdf2_sha256$240000$")
    assert "StrongPassword@123" not in encoded
    assert verify_password("StrongPassword@123", encoded)
    assert not verify_password("wrong-password", encoded)


def test_signed_session_round_trip_and_tamper_rejected():
    user = SimpleNamespace(user_id=7, username="reviewer", role="REVIEWER")
    token = create_session_token(user, max_age_seconds=60)
    payload = decode_session_token(token)
    assert payload["uid"] == 7
    assert payload["role"] == "REVIEWER"
    assert decode_session_token(token + "tampered") is None


def test_reviewer_can_read_but_cannot_change_admin_resources():
    assert not _admin_only_request("/api/rules", "GET")
    assert _admin_only_request("/api/rules", "POST")
    assert _admin_only_request("/api/rules/EDU001", "PUT")
    assert _admin_only_request("/api/blacklist/1", "DELETE")
    assert _admin_only_request("/api/alerts/check", "POST")
    assert not _admin_only_request("/api/cases/case-1/review", "POST")
    assert not _admin_only_request("/api/risk/check", "POST")


def test_admin_can_open_all_pages_and_reviewer_only_review_pages():
    admin = AuthUser(1, "admin", "管理员", "ADMIN")
    reviewer = AuthUser(2, "reviewer", "审核员", "REVIEWER")
    for path in (
        "/dashboard", "/risk-check", "/assessments", "/cases", "/review-history",
        "/rules", "/blacklist", "/users", "/chat",
    ):
        assert _role_can_access_path(admin, path), path

    assert _role_can_access_path(reviewer, "/cases")
    assert _role_can_access_path(reviewer, "/review-history")
    assert _role_can_access_path(reviewer, "/api/cases")
    assert not _role_can_access_path(reviewer, "/dashboard")
    assert not _role_can_access_path(reviewer, "/risk-check")
    assert not _role_can_access_path(reviewer, "/assessments")
    assert not _role_can_access_path(reviewer, "/users")
    assert not _role_can_access_path(reviewer, "/api/users")
    assert not _role_can_access_path(reviewer, "/api/assessments")


def test_role_navigation_and_api_allowlists_are_separated():
    admin = AuthUser(1, "admin", "管理员", "ADMIN")
    reviewer = AuthUser(2, "reviewer", "审核员", "REVIEWER")
    assert _role_can_access_path(admin, "/users")
    assert _role_can_access_path(admin, "/blacklist")
    assert _role_can_access_path(admin, "/risk-check")
    assert not _role_can_access_path(reviewer, "/risk-check")
    assert _role_can_access_path(reviewer, "/api/cases")
    assert _role_can_access_path(reviewer, "/review-history")
    assert not _role_can_access_path(reviewer, "/users")
    assert not _role_can_access_path(reviewer, "/api/users")


def test_login_page_contains_auto_role_message_and_accessible_form():
    html = (ROOT / "templates" / "login.html").read_text(encoding="utf-8")
    assert "角色权限将在登录后自动匹配" in html
    assert 'class="role-list"' not in html
    assert 'id="loginForm"' in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html


def test_mysql_auth_seed_contains_two_roles_and_no_plaintext_password():
    sql = (ROOT / "sql" / "init_auth.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS `sys_user`" in sql
    assert "'ADMIN'" in sql and "'REVIEWER'" in sql
    assert "pbkdf2_sha256$240000$" in sql
    assert "Admin@123" not in sql and "Reviewer@123" not in sql


def test_pages_expose_real_user_and_logout_entry():
    html = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "current_user.display_name" in html
    assert "current_user.role_label" in html
    assert "logoutCurrentUser()" in html


def test_user_management_and_case_assignment_ui_are_present():
    users_html = (ROOT / "templates" / "users.html").read_text(encoding="utf-8")
    cases_html = (ROOT / "templates" / "cases.html").read_text(encoding="utf-8")
    base_html = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "新增用户" in users_html
    assert "/reset-password" in users_html
    assert "分配审核员" in cases_html
    assert "openAssignModal" in cases_html
    assert "审核工作台" in base_html and "审核记录" in base_html
    assert "智能助手" in base_html and "用户管理" in base_html


def test_root_entry_goes_to_login_and_login_goes_to_dashboard():
    auth_source = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    login_html = (ROOT / "templates" / "login.html").read_text(encoding="utf-8")
    assert 'RedirectResponse(url="/login"' in auth_source
    assert "'/dashboard'" in login_html
    assert "data.user?.role === 'REVIEWER' ? '/cases' : '/dashboard'" in login_html


@pytest.mark.asyncio
async def test_reviewer_cannot_add_blacklist_through_case_review():
    from app.routers.case import api_review_case

    data = CaseReviewRequest(
        decision="已拒绝",
        reviewer="伪造审核人",
        add_to_blacklist=True,
    )
    reviewer = AuthUser(2, "reviewer", "审核员", "REVIEWER")
    with pytest.raises(Exception) as exc_info:
        await api_review_case("case-demo", data, SimpleNamespace(), reviewer)
    assert getattr(exc_info.value, "status_code", None) == 403
