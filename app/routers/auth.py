"""登录 / 会话 API (2026-08-11 最小鉴权)"""
import hmac

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import create_token, require_admin
from app.config import settings

auth_router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    username: str
    expires_in: int  # 秒


@auth_router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    """登录: 校验 ADMIN_USERNAME/ADMIN_PASSWORD (env 配置), 返回 HMAC Token."""
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="服务端未配置 ADMIN_PASSWORD, 登录不可用")
    user_ok = hmac.compare_digest(data.username.encode("utf-8"), settings.ADMIN_USERNAME.encode("utf-8"))
    pass_ok = hmac.compare_digest(data.password.encode("utf-8"), settings.ADMIN_PASSWORD.encode("utf-8"))
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(settings.ADMIN_USERNAME)
    return LoginResponse(
        token=token,
        username=settings.ADMIN_USERNAME,
        expires_in=settings.AUTH_TOKEN_TTL_HOURS * 3600,
    )


@auth_router.get("/me")
async def me(username: str = Depends(require_admin)):
    """会话自检: 前端加载页面时验证 Token 是否有效."""
    return {"username": username}
