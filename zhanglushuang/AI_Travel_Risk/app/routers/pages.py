"""页面路由."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["页面"])

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@router.get("/")
async def page_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/risk-check")
async def page_risk_check(request: Request):
    return templates.TemplateResponse(request, "risk_check.html")


@router.get("/rules")
async def page_rules(request: Request):
    return templates.TemplateResponse(request, "rules.html")


@router.get("/cases")
async def page_cases(request: Request):
    return templates.TemplateResponse(request, "cases.html")


@router.get("/blacklist")
async def page_blacklist(request: Request):
    return templates.TemplateResponse(request, "blacklist.html")


@router.get("/assessments")
async def page_assessments(request: Request):
    return templates.TemplateResponse(request, "assessments.html")


@router.get("/chat")
async def page_chat(request: Request):
    return templates.TemplateResponse(request, "chat.html")
