"""登录密码、签名 Cookie 与两角色访问控制。"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.models_system import SysUser


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ROUNDS = 240_000


@dataclass(frozen=True)
class AuthUser:
    user_id: int
    username: str
    display_name: str
    role: str

    @property
    def role_label(self) -> str:
        return "风控管理员" if self.role == "ADMIN" else "审核员"

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """使用标准库 PBKDF2-HMAC-SHA256 生成带盐密码摘要。"""
    if not password:
        raise ValueError("密码不能为空")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ROUNDS)
    return "$".join((PASSWORD_SCHEME, str(PASSWORD_ROUNDS), _b64encode(salt), _b64encode(digest)))


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_text, salt_text, digest_text = encoded.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        expected = _b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64decode(salt_text), int(rounds_text),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def create_session_token(user: SysUser, *, max_age_seconds: int | None = None) -> str:
    expires_at = int(time.time()) + (max_age_seconds or settings.AUTH_SESSION_HOURS * 3600)
    payload = {
        "uid": user.user_id,
        "username": user.username,
        "role": user.role,
        "exp": expires_at,
    }
    payload_text = _b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        settings.AUTH_SECRET_KEY.encode("utf-8"), payload_text.encode("ascii"), hashlib.sha256,
    ).hexdigest()
    return f"{payload_text}.{signature}"


def decode_session_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    try:
        payload_text, signature = token.rsplit(".", 1)
        expected = hmac.new(
            settings.AUTH_SECRET_KEY.encode("utf-8"), payload_text.encode("ascii"), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64decode(payload_text).decode("utf-8"))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if payload.get("role") not in {"ADMIN", "REVIEWER"}:
            return None
        return payload
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        return None


def get_current_user(request: Request) -> AuthUser:
    user = getattr(request.state, "current_user", None)
    if not isinstance(user, AuthUser):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """供写操作路由复用的管理员依赖。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="当前账号无管理员权限")
    return user


def operator_name(user: object, fallback: str = "admin") -> str:
    """兼容直接调用路由函数的单元测试，同时让线上审计使用真实账号。"""
    return user.username if isinstance(user, AuthUser) else fallback


def _admin_only_request(path: str, method: str) -> bool:
    if method == "GET":
        return False
    return (
        path.startswith("/api/rules")
        or path.startswith("/api/blacklist")
        or path.startswith("/api/alerts")
    )


_ADMIN_PAGES = {
    "/dashboard",
    "/risk-check",
    "/assessments",
    "/cases",
    "/review-history",
    "/rules",
    "/blacklist",
    "/users",
    "/chat",
}
_REVIEWER_PAGES = {"/cases", "/review-history"}
_REVIEWER_API_PREFIXES = ("/api/auth", "/api/cases")


def _role_can_access_path(user: AuthUser, path: str) -> bool:
    """页面和 API 的最小白名单；路由层还会执行数据级校验。"""
    if path.startswith("/api/"):
        return user.is_admin or path.startswith(_REVIEWER_API_PREFIXES)
    return path in (_ADMIN_PAGES if user.is_admin else _REVIEWER_PAGES)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """保护所有业务页面/API，并对审核员限制系统配置操作。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        request.state.current_user = None

        if path in {"/", "/login", "/api/auth/login"} or path.startswith("/static/"):
            return await call_next(request)

        payload = decode_session_token(request.cookies.get(settings.AUTH_COOKIE_NAME))
        auth_user: AuthUser | None = None
        if payload:
            try:
                async with AsyncSessionLocal() as db:
                    user = (await db.execute(
                        select(SysUser).where(SysUser.user_id == int(payload["uid"]))
                    )).scalar_one_or_none()
                    if user and user.is_active and user.role == payload.get("role"):
                        auth_user = AuthUser(
                            user_id=user.user_id,
                            username=user.username,
                            display_name=user.display_name,
                            role=user.role,
                        )
            except Exception:
                auth_user = None

        if auth_user is None:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "请先登录"}, status_code=401)
            next_path = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(url=f"/login?next={quote(next_path, safe='/')}", status_code=303)

        request.state.current_user = auth_user
        if not _role_can_access_path(auth_user, path):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "当前角色无权访问该功能"}, status_code=403)
            role_home = "/dashboard" if auth_user.is_admin else "/cases"
            return RedirectResponse(url=role_home, status_code=303)
        if auth_user.role == "REVIEWER" and _admin_only_request(path, request.method.upper()):
            return JSONResponse({"detail": "当前账号为审核员，无权执行系统配置操作"}, status_code=403)

        return await call_next(request)
