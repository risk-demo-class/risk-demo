"""后台用户管理：仅保留两种角色的最小管理能力。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, hash_password, operator_name, require_admin
from app.database import get_db_async
from app.models import SysUser
from app.schemas import (
    SystemUserItem, SystemUserListResponse, UserCreate, UserResetPasswordRequest, UserUpdate,
)
from app.service.action_log import record_action


user_router = APIRouter(prefix="/api/users", tags=["用户管理"])


def _item(user: SysUser) -> SystemUserItem:
    return SystemUserItem(
        user_id=user.user_id, username=user.username, display_name=user.display_name,
        role=user.role, role_label=user.role_label, is_active=user.is_active,
        last_login_time=user.last_login_time, create_time=user.create_time,
    )


@user_router.get("", response_model=SystemUserListResponse)
async def list_users(
    role: str | None = Query(None),
    db: AsyncSession = Depends(get_db_async),
    _admin: AuthUser = Depends(require_admin),
):
    filters = [SysUser.role == role] if role in {"ADMIN", "REVIEWER"} else []
    total = int((await db.execute(select(func.count(SysUser.user_id)).where(*filters))).scalar() or 0)
    users = (await db.execute(select(SysUser).where(*filters).order_by(SysUser.create_time.desc()))).scalars().all()
    return SystemUserListResponse(items=[_item(user) for user in users], total=total)


@user_router.post("", response_model=SystemUserItem, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db_async),
    admin: AuthUser = Depends(require_admin),
):
    username = data.username.strip()
    if not username or not data.display_name.strip() or len(data.password) < 6:
        raise HTTPException(status_code=400, detail="账号、姓名不能为空，初始密码至少 6 位")
    user = SysUser(
        username=username, display_name=data.display_name.strip(), role=data.role,
        password_hash=hash_password(data.password), is_active=1,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="该登录账号已存在") from exc
    await record_action(
        db, operator=operator_name(admin), action_type="CREATE_USER", target_type="user",
        target_id=str(user.user_id), after_value={"username": user.username, "role": user.role}, remark="创建后台用户",
    )
    await db.commit()
    await db.refresh(user)
    return _item(user)


@user_router.put("/{user_id}", response_model=SystemUserItem)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db_async),
    admin: AuthUser = Depends(require_admin),
):
    user = (await db.execute(select(SysUser).where(SysUser.user_id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not data.display_name.strip():
        raise HTTPException(status_code=400, detail="姓名不能为空")
    if user.user_id == admin.user_id and data.role != "ADMIN":
        raise HTTPException(status_code=400, detail="不能把当前登录管理员改为审核员")
    before = {"display_name": user.display_name, "role": user.role}
    user.display_name, user.role = data.display_name.strip(), data.role
    await record_action(
        db, operator=operator_name(admin), action_type="UPDATE_USER", target_type="user", target_id=str(user_id),
        before_value=before, after_value={"display_name": user.display_name, "role": user.role}, remark="更新后台用户",
    )
    await db.commit()
    await db.refresh(user)
    return _item(user)


@user_router.put("/{user_id}/toggle", response_model=SystemUserItem)
async def toggle_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_async),
    admin: AuthUser = Depends(require_admin),
):
    user = (await db.execute(select(SysUser).where(SysUser.user_id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.user_id == admin.user_id and user.is_active:
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    user.is_active = 0 if user.is_active else 1
    await record_action(
        db, operator=operator_name(admin), action_type="TOGGLE_USER", target_type="user", target_id=str(user_id),
        after_value={"is_active": user.is_active}, remark="启用用户" if user.is_active else "停用用户",
    )
    await db.commit()
    await db.refresh(user)
    return _item(user)


@user_router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    data: UserResetPasswordRequest,
    db: AsyncSession = Depends(get_db_async),
    admin: AuthUser = Depends(require_admin),
):
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    user = (await db.execute(select(SysUser).where(SysUser.user_id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(data.password)
    await record_action(
        db, operator=operator_name(admin), action_type="RESET_PASSWORD", target_type="user", target_id=str(user_id),
        remark="重置后台用户密码",
    )
    await db.commit()
    return {"detail": "密码已重置"}
