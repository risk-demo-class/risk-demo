"""七个银行风控管理页面的 Jinja2 路由。"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
router = APIRouter(tags=["管理页面"])


def render(request: Request, template_name: str, active_page: str, title: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        template_name,
        {"active_page": active_page, "page_title": title},
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request) -> HTMLResponse:
    return render(request, "dashboard.html", "dashboard", "风控仪表盘")


@router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
async def rules_page(request: Request) -> HTMLResponse:
    return render(request, "rules.html", "rules", "规则管理")


@router.get("/cases", response_class=HTMLResponse, include_in_schema=False)
async def cases_page(request: Request) -> HTMLResponse:
    return render(request, "cases.html", "cases", "案件管理")


@router.get("/assessments", response_class=HTMLResponse, include_in_schema=False)
async def assessments_page(request: Request) -> HTMLResponse:
    return render(request, "assessments.html", "assessments", "评估历史")


@router.get("/risk-check", response_class=HTMLResponse, include_in_schema=False)
async def risk_check_page(request: Request) -> HTMLResponse:
    return render(request, "risk_check.html", "risk-check", "实时风险检查")


@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_page(request: Request) -> HTMLResponse:
    return render(request, "chat.html", "chat", "AI 风控助手")


@router.get("/blacklist", response_class=HTMLResponse, include_in_schema=False)
async def blacklist_page(request: Request) -> HTMLResponse:
    return render(request, "blacklist.html", "blacklist", "黑名单管理")
