"""Router 层：沿用源码的 Jinja2 运营后台页面路由。"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR)
page_router = APIRouter(tags=["教育风控页面"])


@page_router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html")


@page_router.get("/risk-check", response_class=HTMLResponse)
def risk_check_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "risk_check.html")


@page_router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "rules.html")


@page_router.get("/cases", response_class=HTMLResponse)
def cases_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "cases.html")


@page_router.get("/assessments", response_class=HTMLResponse)
def assessments_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "assessments.html")


@page_router.get("/blacklist", response_class=HTMLResponse)
def blacklist_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "blacklist.html")
