"""密码哈希、当前用户与角色权限。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db_async
from app.models_auth import AppUser
from app.models_risk import RiskActionLog


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False


def set_user_session(request: Request, user: AppUser) -> None:
    """Issue a session bound to the user's current revocation version."""
    request.session.clear()
    request.session.update({
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "session_version": user.session_version,
    })


async def ensure_default_admin(db: AsyncSession) -> AppUser:
    username = settings.DEFAULT_ADMIN_USERNAME.lower()
    user = (await db.execute(select(AppUser).where(AppUser.username == username))).scalar_one_or_none()
    if user is None:
        user = AppUser(
            username=username,
            password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            display_name="超级管理员",
            role="admin",
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db_async),
) -> AppUser:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "请先登录")
    user = await db.get(AppUser, int(user_id))
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(401, "用户不存在或已停用")
    cookie_version = request.session.get("session_version")
    try:
        version_matches = int(cookie_version) == user.session_version
    except (TypeError, ValueError):
        version_matches = False
    if not version_matches:
        request.session.clear()
        raise HTTPException(401, "登录状态已失效，请重新登录")
    return user


def require_roles(*roles: str):
    async def dependency(user: AppUser = Depends(get_current_user)) -> AppUser:
        if not user.is_superuser and user.role not in roles:
            raise HTTPException(403, "当前用户没有执行此操作的权限")
        return user
    return dependency


def user_dict(user: AppUser) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": bool(user.is_active),
        "is_superuser": bool(user.is_superuser),
        "last_login_at": user.last_login_at,
        "create_time": user.create_time,
    }


def add_user_audit(
    db: AsyncSession,
    request: Request,
    operator: str,
    action_type: str,
    target_id: str,
    before: dict | None,
    after: dict | None,
    remark: str,
) -> None:
    db.add(RiskActionLog(
        operator=operator[:50],
        action_type=action_type,
        target_type="user",
        target_id=target_id[:50],
        before_value=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
        after_value=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
        ip=request.client.host[:50] if request.client else None,
        remark=remark,
        create_time=datetime.now(),
    ))
