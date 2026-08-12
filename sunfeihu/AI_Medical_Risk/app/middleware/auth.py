"""统一登录门禁。"""
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


PUBLIC_EXACT = {
    "/health", "/login", "/register",
    "/api/auth/login", "/api/auth/register",
}
PUBLIC_PREFIXES = ("/static/",)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)
        if request.session.get("user_id"):
            return await call_next(request)
        if path.startswith("/api/") or path.startswith("/docs") or path.startswith("/openapi"):
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
