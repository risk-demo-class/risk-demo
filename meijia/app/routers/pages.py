from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(ROOT / "templates"))
router = APIRouter(tags=["页面"])


def render(request: Request, template: str, title: str, active: str):
    return templates.TemplateResponse(request=request, name=template, context={"title": title, "active": active})


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request): return render(request, "dashboard.html", "风险态势", "dashboard")


@router.get("/risk-check", response_class=HTMLResponse, include_in_schema=False)
def risk_check(request: Request): return render(request, "risk_check.html", "风险检查", "risk-check")


@router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
def rules(request: Request): return render(request, "rules.html", "规则中心", "rules")


@router.get("/assessments", response_class=HTMLResponse, include_in_schema=False)
def assessments(request: Request): return render(request, "assessments.html", "评估历史", "assessments")


@router.get("/cases", response_class=HTMLResponse, include_in_schema=False)
def cases(request: Request): return render(request, "cases.html", "人工案件", "cases")


@router.get("/blacklist", response_class=HTMLResponse, include_in_schema=False)
def blacklist(request: Request): return render(request, "blacklist.html", "黑名单", "blacklist")


@router.get("/users", response_class=HTMLResponse, include_in_schema=False)
def users(request: Request): return render(request, "users.html", "学员画像", "users")


@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
def chat(request: Request): return render(request, "chat.html", "AI 助手", "chat")
