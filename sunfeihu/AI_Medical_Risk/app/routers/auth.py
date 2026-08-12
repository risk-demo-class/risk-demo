"""登录、注册、改密和用户管理 API。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models_auth import AppUser
from app.schemas import (
    AuthLoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    UserCreateRequest,
    UserRegisterRequest,
    UserUpdateRequest,
)
from app.service.auth import (
    add_user_audit,
    get_current_user,
    hash_password,
    require_roles,
    set_user_session,
    user_dict,
    verify_password,
)


auth_router = APIRouter(prefix="/api/auth", tags=["登录与用户"])


async def _username_exists(db: AsyncSession, username: str) -> bool:
    return (await db.execute(select(AppUser.user_id).where(
        AppUser.username == username.lower()
    ))).scalar_one_or_none() is not None


@auth_router.post("/login")
async def login(data: AuthLoginRequest, request: Request, db: AsyncSession = Depends(get_db_async)):
    username = data.username.strip().lower()
    user = (await db.execute(select(AppUser).where(AppUser.username == username))).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    set_user_session(request, user)
    user.last_login_at = datetime.now()
    add_user_audit(db, request, user.username, "LOGIN", str(user.user_id), None, {"success": True}, "用户登录")
    await db.commit()
    return user_dict(user)


@auth_router.post("/register")
async def register(data: UserRegisterRequest, request: Request, db: AsyncSession = Depends(get_db_async)):
    username = data.username.strip().lower()
    if await _username_exists(db, username):
        raise HTTPException(409, "用户名已存在")
    user = AppUser(
        username=username,
        password_hash=hash_password(data.password),
        display_name=data.display_name.strip(),
        role="viewer",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    add_user_audit(db, request, username, "CREATE_USER", str(user.user_id), None, user_dict(user), "用户自助注册")
    await db.commit()
    await db.refresh(user)
    set_user_session(request, user)
    return user_dict(user)


@auth_router.post("/logout")
async def logout(
    request: Request,
    user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_async),
):
    add_user_audit(db, request, user.username, "LOGOUT", str(user.user_id), None, None, "用户退出")
    await db.commit()
    request.session.clear()
    return {"logged_out": True}


@auth_router.get("/me")
async def me(user: AppUser = Depends(get_current_user)):
    return user_dict(user)


@auth_router.post("/change-password")
async def change_password(
    data: PasswordChangeRequest,
    request: Request,
    user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_async),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")
    user.password_hash = hash_password(data.new_password)
    user.session_version += 1
    add_user_audit(db, request, user.username, "CHANGE_PASSWORD", str(user.user_id), None, {"changed": True}, "用户修改密码")
    await db.commit()
    set_user_session(request, user)
    return {"changed": True}


@auth_router.get("/users")
async def list_users(
    _admin: AppUser = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db_async),
):
    users = list((await db.execute(select(AppUser).order_by(AppUser.user_id))).scalars().all())
    return [user_dict(user) for user in users]


@auth_router.post("/users")
async def create_user(
    data: UserCreateRequest,
    request: Request,
    admin: AppUser = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db_async),
):
    username = data.username.strip().lower()
    if await _username_exists(db, username):
        raise HTTPException(409, "用户名已存在")
    user = AppUser(
        username=username, password_hash=hash_password(data.password),
        display_name=data.display_name.strip(), role=data.role,
        is_active=True, is_superuser=False,
    )
    db.add(user)
    await db.flush()
    add_user_audit(db, request, admin.username, "CREATE_USER", str(user.user_id), None, user_dict(user), "管理员创建用户")
    await db.commit()
    await db.refresh(user)
    return user_dict(user)


@auth_router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    data: UserUpdateRequest,
    request: Request,
    admin: AppUser = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db_async),
):
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    changes = data.model_dump(exclude_none=True)
    if user.is_superuser and any(field in changes for field in ("role", "is_active")):
        raise HTTPException(409, "不能修改超级用户的角色或状态")
    before = user_dict(user)
    security_changed = any(
        field in changes and getattr(user, field) != changes[field]
        for field in ("role", "is_active")
    )
    for field, value in changes.items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    if security_changed:
        user.session_version += 1
    add_user_audit(db, request, admin.username, "UPDATE_USER", str(user_id), before, user_dict(user), "更新用户角色或状态")
    await db.commit()
    return user_dict(user)


@auth_router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    data: PasswordResetRequest,
    request: Request,
    admin: AppUser = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db_async),
):
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    user.password_hash = hash_password(data.new_password)
    user.session_version += 1
    add_user_audit(db, request, admin.username, "RESET_PASSWORD", str(user_id), None, {"reset": True}, "管理员重置密码")
    await db.commit()
    if user.user_id == admin.user_id:
        set_user_session(request, user)
    return {"reset": True}
