"""登录、退出和当前用户 API。"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, create_session_token, get_current_user, verify_password
from app.config import settings
from app.database import get_db_async
from app.models_system import SysUser


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

auth_router = APIRouter(tags=["登录认证"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


@auth_router.get("/", include_in_schema=False)
async def application_entry():
    """系统统一入口：无论是否有旧会话，都先展示登录页。"""
    return RedirectResponse(url="/login", status_code=303)


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@auth_router.post("/api/auth/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db_async)):
    try:
        user = (await db.execute(
            select(SysUser).where(SysUser.username == data.username.strip())
        )).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="登录用户表尚未初始化，请先运行 python scripts/init_db.py --keep-data",
        ) from exc

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用，请联系风控管理员")

    user.last_login_time = datetime.now()
    await db.commit()

    max_age = settings.AUTH_SESSION_HOURS * 3600
    if data.remember:
        max_age = 7 * 24 * 3600
    response = JSONResponse({
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "role_label": user.role_label,
        }
    })
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=create_session_token(user, max_age_seconds=max_age),
        max_age=max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return response


@auth_router.get("/api/auth/me")
async def current_user(user: AuthUser = Depends(get_current_user)):
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": user.role_label,
    }


@auth_router.post("/api/auth/logout")
async def logout(_user: AuthUser = Depends(get_current_user)):
    response = JSONResponse({"detail": "已退出登录"})
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
    return response
