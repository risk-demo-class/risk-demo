"""医疗风控管理端页面路由。"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
pages_router = APIRouter(include_in_schema=False)


def _page(request: Request, name: str, title: str):
    return templates.TemplateResponse(request=request, name=name, context={
        "title": title,
        "current": name.removesuffix(".html"),
        "session_user": {
            "username": request.session.get("username"),
            "role": request.session.get("role"),
        },
    })


@pages_router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"mode": "login"})


@pages_router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"mode": "register"})


@pages_router.get("/")
async def home():
    return RedirectResponse("/dashboard", status_code=307)


@pages_router.get("/dashboard")
async def dashboard(request: Request):
    return _page(request, "dashboard.html", "风险仪表盘")


@pages_router.get("/patients")
async def patients_page(request: Request):
    return _page(request, "patients.html", "患者管理")


@pages_router.get("/risk-check")
async def risk_check_page(request: Request):
    return _page(request, "risk_check.html", "医疗风险检查")


@pages_router.get("/rules")
async def rules_page(request: Request):
    return _page(request, "rules.html", "规则管理")


@pages_router.get("/cases")
async def cases_page(request: Request):
    return _page(request, "cases.html", "案件审核")


@pages_router.get("/assessments")
async def assessments_page(request: Request):
    return _page(request, "assessments.html", "评估历史")


@pages_router.get("/blacklist")
async def blacklist_page(request: Request):
    return _page(request, "blacklist.html", "医疗黑名单")


@pages_router.get("/assistant")
async def assistant_page(request: Request):
    return _page(request, "assistant.html", "AI 风控助手")


@pages_router.get("/system")
async def system_page(request: Request):
    return _page(request, "system.html", "告警与审计")


@pages_router.get("/users")
async def users_page(request: Request):
    return _page(request, "users.html", "用户与账户")
