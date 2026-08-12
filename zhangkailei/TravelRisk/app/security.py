"""可选的管理 API Key 鉴权；开发环境留空即关闭。"""
import secrets

from fastapi import Header, HTTPException

from app.config import settings


async def require_admin(x_admin_key: str | None = Header(default=None)) -> str:
    expected = settings.ADMIN_API_KEY
    if not expected:
        return "dev-admin"
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="缺少或无效的 X-Admin-Key")
    return "admin"
