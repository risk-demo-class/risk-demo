"""Server-rendered platform pages."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.agent.tools import TOOL_MANIFEST
from app.config import settings


router = APIRouter(tags=["pages"])
_root = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(_root / "templates"))


def _context(request: Request, page_title: str) -> dict:
    return {
        "request": request,
        "page_title": page_title,
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "stage": "完整项目 · 三层融合",
        "components": settings.enabled_components(),
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", _context(request, "风控总览"))


@router.get("/risk-check", response_class=HTMLResponse)
async def risk_check_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "risk_check.html", _context(request, "风险检查"))


@router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "rules.html", _context(request, "规则中心"))


@router.get("/assessments", response_class=HTMLResponse)
async def assessments_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "assessments.html", _context(request, "评估历史"))


@router.get("/cases", response_class=HTMLResponse)
async def cases_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "cases.html", _context(request, "案件工作台"))


@router.get("/appeal", response_class=HTMLResponse)
async def appeal_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "appeal.html", _context(request, "客户申诉"))


@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "graph.html", _context(request, "关系图谱"))


@router.get("/agent", response_class=HTMLResponse)
async def agent_page(request: Request) -> HTMLResponse:
    context = _context(request, "AI 风控助手")
    context["tools"] = TOOL_MANIFEST
    return templates.TemplateResponse(request, "agent.html", context)
