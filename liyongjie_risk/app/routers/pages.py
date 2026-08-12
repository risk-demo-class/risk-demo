"""
银行风控系统 - 页面路由 (Jinja2 模板渲染)
========================================
提供前端页面访问:
  GET /               → 仪表盘 (dashboard.html)
  GET /risk-check     → 风险检查 (risk_check.html)
  GET /rules          → 规则管理 (rules.html)
  GET /events         → 风险事件 (events.html)
  GET /blacklist      → 黑名单 (blacklist.html)
  GET /chat           → AI 助手 (chat.html)
"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# 模板目录: MY_RISK/templates/
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

page_router = APIRouter(tags=["页面"])


@page_router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@page_router.get("/risk-check", response_class=HTMLResponse)
async def risk_check_page(request: Request):
    return templates.TemplateResponse(request, "risk_check.html")


@page_router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html")


@page_router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    return templates.TemplateResponse(request, "events.html")


@page_router.get("/blacklist", response_class=HTMLResponse)
async def blacklist_page(request: Request):
    return templates.TemplateResponse(request, "blacklist.html")


@page_router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html")
