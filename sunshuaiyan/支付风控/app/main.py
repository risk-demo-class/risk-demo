from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import router as api_router


BASE = Path(__file__).resolve().parent
app = FastAPI(
    title="PingPong 跨境收款风控",
    version="1.0.0",
    description="规则与 XGBoost 双轨的跨境收付风险演示系统",
)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


def render(request: Request, template: str, page: str, title: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"page": page, "title": title},
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return render(request, "dashboard.html", "dashboard", "风险总览")


@app.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request) -> HTMLResponse:
    return render(request, "rules.html", "rules", "规则策略")


@app.get("/cases", response_class=HTMLResponse)
def cases_page(request: Request) -> HTMLResponse:
    return render(request, "cases.html", "cases", "案件队列")


@app.get("/model", response_class=HTMLResponse)
def model_page(request: Request) -> HTMLResponse:
    return render(request, "model.html", "model", "模型评估")


@app.get("/risk-check", response_class=HTMLResponse)
def risk_check_page(request: Request) -> HTMLResponse:
    return render(request, "risk_check.html", "risk-check", "风险检查")


@app.get("/assistant", response_class=HTMLResponse)
def assistant_page(request: Request) -> HTMLResponse:
    return render(request, "assistant.html", "assistant", "AI 风控助手")


@app.get("/blacklist", response_class=HTMLResponse)
def blacklist_page(request: Request) -> HTMLResponse:
    return render(request, "blacklist.html", "blacklist", "黑名单")
