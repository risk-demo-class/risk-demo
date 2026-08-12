from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Permission, Role, RolePermission, StaffUser, StaffUserRole


SESSION_COOKIE_NAME = "risk_session"
PASSWORD_ITERATIONS = 600_000

PERMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("dashboard:view", "查看风险主面板", "dashboard", "查看总体风险统计和趋势"),
    ("orders:view", "查看订单", "orders", "查询订单及风险详情"),
    ("reviews:view", "查看审核案件", "reviews", "查看人工审核队列"),
    ("reviews:decide", "处置审核案件", "reviews", "放行或拒绝待审订单"),
    ("rules:view", "查看风险规则", "rules", "查看规则组和档位"),
    ("rules:manage", "管理风险规则", "rules", "编辑规则条件、分值和启停状态"),
    ("blacklist:view", "查看黑名单", "blacklist", "查询风险证件名单"),
    ("blacklist:manage", "管理黑名单", "blacklist", "新增、更新和删除名单"),
    ("audit:view", "查看审计日志", "audit", "查看后台操作留痕"),
    ("iam:view", "查看权限管理", "iam", "查看员工、角色与权限"),
    ("iam:manage", "管理权限", "iam", "管理员工账号、角色和权限分配"),
)


@dataclass(frozen=True, slots=True)
class AuthenticatedStaff:
    staff_user_id: int
    username: str
    display_name: str
    session_version: int
    permissions: frozenset[str]


def hash_password(password: str) -> str:
    if len(password) < 6:
        raise ValueError("password must contain at least 6 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _session_secret() -> bytes:
    secret = os.getenv("APP_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("APP_SECRET_KEY must contain at least 32 characters")
    return secret.encode("utf-8")


def _encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def create_session_token(user: StaffUser) -> str:
    ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    payload = {
        "uid": user.staff_user_id,
        "ver": user.session_version,
        "exp": int(time.time()) + ttl_seconds,
    }
    encoded_payload = _encode_base64(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = _encode_base64(
        hmac.new(_session_secret(), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded_payload}.{signature}"


def decode_session_token(token: str) -> dict[str, int] | None:
    try:
        encoded_payload, signature = token.split(".", 1)
        expected = _encode_base64(
            hmac.new(
                _session_secret(), encoded_payload.encode("ascii"), hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_decode_base64(encoded_payload))
        if int(payload["exp"]) < int(time.time()):
            return None
        return {
            "uid": int(payload["uid"]),
            "ver": int(payload["ver"]),
            "exp": int(payload["exp"]),
        }
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def load_staff_permissions(db: Session, staff_user_id: int) -> frozenset[str]:
    codes = db.scalars(
        select(Permission.permission_code)
        .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
        .join(StaffUserRole, StaffUserRole.role_id == RolePermission.role_id)
        .where(StaffUserRole.staff_user_id == staff_user_id)
        .distinct()
    )
    return frozenset(codes)


def get_current_staff(
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> AuthenticatedStaff:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    payload = decode_session_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    user = db.get(StaffUser, payload["uid"])
    if user is None or not user.is_active or user.session_version != payload["ver"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用或登录已失效")
    return AuthenticatedStaff(
        staff_user_id=user.staff_user_id,
        username=user.username,
        display_name=user.display_name,
        session_version=user.session_version,
        permissions=load_staff_permissions(db, user.staff_user_id),
    )


def require_permission(permission_code: str):
    def dependency(staff: AuthenticatedStaff = Depends(get_current_staff)) -> AuthenticatedStaff:
        if permission_code not in staff.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有该操作权限")
        return staff

    return dependency


def require_administrator(
    staff: AuthenticatedStaff = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> AuthenticatedStaff:
    """Restrict an endpoint to members of the built-in administrator role."""
    administrator = db.scalar(
        select(Role.role_id)
        .join(StaffUserRole, StaffUserRole.role_id == Role.role_id)
        .where(
            StaffUserRole.staff_user_id == staff.staff_user_id,
            Role.role_code == "ADMINISTRATOR",
        )
    )
    if administrator is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅系统管理员可以使用 Agent")
    return staff
