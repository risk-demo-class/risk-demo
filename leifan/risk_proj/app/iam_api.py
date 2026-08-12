from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE_NAME,
    AuthenticatedStaff,
    create_session_token,
    get_current_staff,
    hash_password,
    require_permission,
    verify_password,
)
from app.database import get_db
from app.models import (
    AuditLog,
    Permission,
    Role,
    RolePermission,
    StaffUser,
    StaffUserRole,
)


router = APIRouter(prefix="/api")


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class StaffCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    role_id: int = Field(gt=0)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or not value[0].isalpha() or any(
            not (character.isalnum() or character in "_.-") for character in value
        ):
            raise ValueError("账号须以中文或英文字母开头，只能包含文字、数字、点、横线和下划线")
        return value


class StaffUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    role_id: int | None = Field(default=None, gt=0)


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class RoleCreateRequest(BaseModel):
    role_code: str = Field(min_length=2, max_length=50)
    role_name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    permission_ids: list[int] = Field(default_factory=list)

    @field_validator("role_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,49}", value):
            raise ValueError("角色编码须使用大写字母、数字和下划线")
        return value


class RoleUpdateRequest(BaseModel):
    role_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    permission_ids: list[int] | None = None


def add_audit(
    db: Session,
    staff: AuthenticatedStaff,
    action: str,
    entity_type: str,
    entity_id: int | str,
    before: dict | None,
    after: dict | None,
) -> None:
    db.add(
        AuditLog(
            operator=staff.username,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            before_data=before,
            after_data=after,
            request_id=f"WEB-{action}-{entity_id}-{int(datetime.now().timestamp())}",
            created_at=datetime.now(),
        )
    )


def validate_ids(db: Session, model: type, id_field, ids: list[int], label: str) -> list[int]:
    normalized = list(dict.fromkeys(ids))
    if not normalized:
        return []
    existing = set(db.scalars(select(id_field).where(id_field.in_(normalized))))
    missing = set(normalized) - existing
    if missing:
        raise HTTPException(status_code=422, detail=f"{label}不存在：{sorted(missing)}")
    return normalized


def user_item(db: Session, user: StaffUser) -> dict:
    roles = db.execute(
        select(Role.role_id, Role.role_code, Role.role_name)
        .join(StaffUserRole, StaffUserRole.role_id == Role.role_id)
        .where(StaffUserRole.staff_user_id == user.staff_user_id)
        .order_by(Role.role_id)
    ).all()
    return {
        "staff_user_id": user.staff_user_id,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "roles": [
            {"role_id": role_id, "role_code": code, "role_name": name}
            for role_id, code, name in roles
        ],
    }


def role_item(db: Session, role: Role) -> dict:
    permissions = db.execute(
        select(Permission.permission_id, Permission.permission_code, Permission.permission_name)
        .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
        .where(RolePermission.role_id == role.role_id)
        .order_by(Permission.module, Permission.permission_id)
    ).all()
    user_count = len(
        list(db.scalars(select(StaffUserRole.staff_user_id).where(StaffUserRole.role_id == role.role_id)))
    )
    return {
        "role_id": role.role_id,
        "role_code": role.role_code,
        "role_name": role.role_name,
        "description": role.description,
        "is_system": role.is_system,
        "user_count": user_count,
        "permissions": [
            {"permission_id": pid, "permission_code": code, "permission_name": name}
            for pid, code, name in permissions
        ],
    }


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(StaffUser).where(StaffUser.username == payload.username.strip().lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    user.last_login_at = datetime.now()
    user.updated_at = datetime.now()
    db.commit()
    ttl = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user),
        max_age=ttl,
        httponly=True,
        secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(
    staff: AuthenticatedStaff = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> dict:
    roles = db.execute(
        select(Role.role_code, Role.role_name)
        .join(StaffUserRole, StaffUserRole.role_id == Role.role_id)
        .where(StaffUserRole.staff_user_id == staff.staff_user_id)
        .order_by(Role.role_id)
    ).all()
    return {
        "staff_user_id": staff.staff_user_id,
        "username": staff.username,
        "display_name": staff.display_name,
        "permissions": sorted(staff.permissions),
        "roles": [{"role_code": code, "role_name": name} for code, name in roles],
    }


@router.get("/iam/overview")
def iam_overview(
    staff: AuthenticatedStaff = Depends(require_permission("iam:view")),
    db: Session = Depends(get_db),
) -> dict:
    users = list(db.scalars(select(StaffUser).order_by(StaffUser.staff_user_id)))
    roles = list(db.scalars(select(Role).order_by(Role.is_system.desc(), Role.role_id)))
    permissions = list(db.scalars(select(Permission).order_by(Permission.module, Permission.permission_id)))
    return {
        "users": [user_item(db, user) for user in users],
        "roles": [role_item(db, role) for role in roles],
        "permissions": [
            {
                "permission_id": item.permission_id,
                "permission_code": item.permission_code,
                "permission_name": item.permission_name,
                "module": item.module,
                "description": item.description,
            }
            for item in permissions
        ],
        "can_manage": "iam:manage" in staff.permissions,
    }


@router.post("/iam/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: StaffCreateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    if db.scalar(select(StaffUser).where(StaffUser.username == payload.username)):
        raise HTTPException(status_code=409, detail="账号已存在")
    role_id = validate_ids(db, Role, Role.role_id, [payload.role_id], "角色")[0]
    now = datetime.now()
    user = StaffUser(
        username=payload.username,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
        session_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    db.add(
        StaffUserRole(
            staff_user_id=user.staff_user_id,
            role_id=role_id,
            assigned_by=staff.staff_user_id,
        )
    )
    add_audit(
        db,
        staff,
        "STAFF_USER_CREATED",
        "staff_user",
        user.staff_user_id,
        None,
        {"username": user.username, "role_id": role_id},
    )
    db.commit()
    return user_item(db, user)


@router.patch("/iam/users/{user_id}")
def update_user(
    user_id: int,
    payload: StaffUpdateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="至少提供一个需要更新的字段")
    user = db.scalar(select(StaffUser).where(StaffUser.staff_user_id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="员工账号不存在")
    if user.username == "administer" and payload.is_active is False:
        raise HTTPException(status_code=409, detail="主管理员账号不能停用")
    before = user_item(db, user)
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.is_active is not None:
        if user.is_active != payload.is_active:
            user.is_active = payload.is_active
            user.session_version += 1
    if payload.role_id is not None:
        role_id = validate_ids(db, Role, Role.role_id, [payload.role_id], "角色")[0]
        admin_role = db.scalar(select(Role).where(Role.role_code == "ADMINISTRATOR"))
        if user.username == "administer" and admin_role and admin_role.role_id != role_id:
            raise HTTPException(status_code=409, detail="主管理员不能移除超级管理员角色")
        db.execute(delete(StaffUserRole).where(StaffUserRole.staff_user_id == user_id))
        db.add(
            StaffUserRole(
                staff_user_id=user_id,
                role_id=role_id,
                assigned_by=staff.staff_user_id,
            )
        )
    user.updated_at = datetime.now()
    db.flush()
    after = user_item(db, user)
    add_audit(db, staff, "STAFF_USER_UPDATED", "staff_user", user_id, before, after)
    db.commit()
    return user_item(db, user)


@router.post("/iam/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(StaffUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="员工账号不存在")
    user.password_hash = hash_password(payload.password)
    user.session_version += 1
    user.updated_at = datetime.now()
    add_audit(db, staff, "STAFF_PASSWORD_RESET", "staff_user", user_id, None, {"username": user.username})
    db.commit()
    return {"ok": True}


@router.delete("/iam/users/{user_id}")
def delete_user(
    user_id: int,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(StaffUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="员工账号不存在")
    if user.username == "administer" or user.staff_user_id == staff.staff_user_id:
        raise HTTPException(status_code=409, detail="不能删除主管理员或当前登录账号")
    before = {"username": user.username, "display_name": user.display_name}
    db.delete(user)
    add_audit(db, staff, "STAFF_USER_DELETED", "staff_user", user_id, before, None)
    db.commit()
    return {"deleted": True}


@router.post("/iam/roles", status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    if db.scalar(select(Role).where(Role.role_code == payload.role_code)):
        raise HTTPException(status_code=409, detail="角色编码已存在")
    permission_ids = validate_ids(db, Permission, Permission.permission_id, payload.permission_ids, "权限")
    now = datetime.now()
    role = Role(role_code=payload.role_code, role_name=payload.role_name.strip(), description=payload.description, is_system=False, created_at=now, updated_at=now)
    db.add(role)
    db.flush()
    for permission_id in permission_ids:
        db.add(RolePermission(role_id=role.role_id, permission_id=permission_id))
    add_audit(db, staff, "ROLE_CREATED", "role", role.role_id, None, {"role_code": role.role_code, "permission_ids": permission_ids})
    db.commit()
    return role_item(db, role)


@router.patch("/iam/roles/{role_id}")
def update_role(
    role_id: int,
    payload: RoleUpdateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="至少提供一个需要更新的字段")
    if role.role_code == "ADMINISTRATOR" and payload.permission_ids is not None:
        raise HTTPException(status_code=409, detail="超级管理员权限不可缩减")
    before = role_item(db, role)
    if payload.role_name is not None:
        role.role_name = payload.role_name.strip()
    if "description" in payload.model_fields_set:
        role.description = payload.description
    if payload.permission_ids is not None:
        permission_ids = validate_ids(db, Permission, Permission.permission_id, payload.permission_ids, "权限")
        db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for permission_id in permission_ids:
            db.add(RolePermission(role_id=role_id, permission_id=permission_id))
    role.updated_at = datetime.now()
    db.flush()
    after = role_item(db, role)
    add_audit(db, staff, "ROLE_UPDATED", "role", role_id, before, after)
    db.commit()
    return role_item(db, role)


@router.delete("/iam/roles/{role_id}")
def delete_role(
    role_id: int,
    staff: AuthenticatedStaff = Depends(require_permission("iam:manage")),
    db: Session = Depends(get_db),
) -> dict:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.is_system:
        raise HTTPException(status_code=409, detail="系统预置角色不能删除")
    before = {"role_code": role.role_code, "role_name": role.role_name}
    db.delete(role)
    add_audit(db, staff, "ROLE_DELETED", "role", role_id, before, None)
    db.commit()
    return {"deleted": True}
