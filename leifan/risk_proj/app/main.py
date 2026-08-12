from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.agent_api import router as agent_router
from app.auth import AuthenticatedStaff, require_administrator, require_permission
from app.iam_api import router as iam_router


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
PAGES_ROOT = FRONTEND_ROOT / "pages"
STATIC_ROOT = FRONTEND_ROOT / "static"

app = FastAPI(
    title="OTA 旅游风控平台",
    description="机票、酒店、签证与跟团游订单风险管理",
    version="0.1.0",
)
app.include_router(api_router)
app.include_router(iam_router)
app.include_router(agent_router)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        next_path = request.url.path
        return RedirectResponse(url=f"/login?next={next_path}", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def page(filename: str) -> FileResponse:
    return FileResponse(PAGES_ROOT / filename)


@app.get("/", include_in_schema=False)
def dashboard_page(
    staff: AuthenticatedStaff = Depends(require_permission("dashboard:view")),
) -> FileResponse:
    return page("dashboard.html")


@app.get("/orders", include_in_schema=False)
def orders_page(
    staff: AuthenticatedStaff = Depends(require_permission("orders:view")),
) -> FileResponse:
    return page("orders.html")


@app.get("/orders/{order_id}", include_in_schema=False)
def order_detail_page(
    order_id: int,
    staff: AuthenticatedStaff = Depends(require_permission("orders:view")),
) -> FileResponse:
    return page("order-detail.html")


@app.get("/reviews", include_in_schema=False)
def reviews_page(
    staff: AuthenticatedStaff = Depends(require_permission("reviews:view")),
) -> FileResponse:
    return page("reviews.html")


@app.get("/rules", include_in_schema=False)
def rules_page(
    staff: AuthenticatedStaff = Depends(require_permission("rules:view")),
) -> FileResponse:
    return page("rules.html")


@app.get("/blacklist", include_in_schema=False)
def blacklist_page(
    staff: AuthenticatedStaff = Depends(require_permission("blacklist:view")),
) -> FileResponse:
    return page("blacklist.html")


@app.get("/audit", include_in_schema=False)
def audit_page(
    staff: AuthenticatedStaff = Depends(require_permission("audit:view")),
) -> FileResponse:
    return page("audit.html")


@app.get("/permissions", include_in_schema=False)
def permissions_page(
    staff: AuthenticatedStaff = Depends(require_permission("iam:view")),
) -> FileResponse:
    return page("permissions.html")


@app.get("/agent", include_in_schema=False)
def agent_page(
    staff: AuthenticatedStaff = Depends(require_administrator),
) -> FileResponse:
    return page("agent.html")


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return page("login.html")
