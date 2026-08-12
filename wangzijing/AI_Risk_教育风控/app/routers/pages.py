"""页面路由 (Jinja2 模板渲染)"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings


# 模板目录: 项目根目录下的 templates/
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

page_router = APIRouter(tags=["页面"])


@page_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@page_router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html")


@page_router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse(request, "users.html")


@page_router.get("/cases", response_class=HTMLResponse)
async def cases_page(request: Request):
    return templates.TemplateResponse(request, "cases.html", {"view_mode": "active"})


@page_router.get("/review-history", response_class=HTMLResponse)
async def review_history_page(request: Request):
    """复用案件页面，只展示当前账号已经完成的审核记录。"""
    return templates.TemplateResponse(request, "cases.html", {"view_mode": "history"})


@page_router.get("/assessments", response_class=HTMLResponse)
async def assessments_page(request: Request):
    """评估历史页 (P3-S9 2026-08-08): 全量评估, 含已结案 + 通过/标记"""
    return templates.TemplateResponse(request, "assessments.html")


@page_router.get("/risk-check", response_class=HTMLResponse)
async def risk_check_page(request: Request):
    return templates.TemplateResponse(request, "risk_check.html")


@page_router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"ai_enabled": bool(settings.LLM_API_KEY.strip())},
    )


@page_router.get("/blacklist", response_class=HTMLResponse)
async def blacklist_page(request: Request):
    return templates.TemplateResponse(request, "blacklist.html")
