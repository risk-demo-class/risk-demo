"""
【2026-08-11】最小鉴权: 登录 + HMAC Token + require_admin 依赖.

设计:
- 无状态 HMAC Token (标准库 hmac/hashlib/base64 实现, 不引入 JWT 依赖)
- 管理接口 (规则增删改/黑名单增删/案件审核/Agent 对话/告警触发) 用 require_admin 保护
- 前端 localStorage 存 token, 全局 fetch 包装器自动带 Authorization: Bearer 头
- ADMIN_PASSWORD 为空 → 登录接口直接 503 (生产必须配置)
- AUTH_SECRET 为空 → 由 ADMIN_PASSWORD 派生 (跨 worker 稳定); 生产建议单独配置强随机 AUTH_SECRET
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


def _get_secret() -> bytes:
    """取签名密钥: AUTH_SECRET 优先, 否则由 ADMIN_PASSWORD 派生 (多 worker 一致).

    不缓存: 单次 sha256 开销可忽略, 且测试可自由改 env 不影响已缓存的密钥.
    """
    if settings.AUTH_SECRET:
        return settings.AUTH_SECRET.encode("utf-8")
    return hashlib.sha256(
        ("ai-risk-medical:" + settings.ADMIN_PASSWORD).encode("utf-8")
    ).digest()


def create_token(username: str, ttl_hours: Optional[int] = None) -> str:
    """签发 HMAC Token: base64url(payload).base64url(hmac-sha256)."""
    ttl = settings.AUTH_TOKEN_TTL_HOURS if ttl_hours is None else ttl_hours
    payload = {"sub": username, "exp": int(time.time()) + int(ttl) * 3600}
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    sig = hmac.new(_get_secret(), raw.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{raw}.{sig_b64}"


def verify_token(token: str) -> Optional[str]:
    """校验 Token, 返回用户名; 签名错误/过期/格式非法返回 None."""
    try:
        raw, sig_b64 = token.split(".", 1)
        sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        expected = hmac.new(_get_secret(), raw.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload_raw = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        payload = json.loads(payload_raw)
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return str(payload.get("sub", ""))
    except Exception:
        return None


def require_admin(authorization: Optional[str] = Header(default=None)) -> str:
    """FastAPI 依赖: 校验 Authorization: Bearer <token>, 失败 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录或 Token 缺失")
    token = authorization.split(" ", 1)[1].strip()
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    return username
