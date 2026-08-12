"""页面路由 (Jinja2 模板渲染)"""
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


# 模板目录: 项目根目录下的 templates/
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

page_router = APIRouter(tags=["页面"])


def _load_model_metrics() -> dict:
    """读取训练指标 JSON (app/engine/xgb_metrics.json), 不存在时返回空 dict."""
    metrics_path = os.path.join(_BASE_DIR, "app", "engine", "xgb_metrics.json")
    if not os.path.exists(metrics_path):
        return {}
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


@page_router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@page_router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html")


@page_router.get("/cases", response_class=HTMLResponse)
async def cases_page(request: Request):
    return templates.TemplateResponse(request, "cases.html")


@page_router.get("/assessments", response_class=HTMLResponse)
async def assessments_page(request: Request):
    """评估历史页 (P3-S9 2026-08-08): 全量评估, 含已结案 + 通过/标记"""
    return templates.TemplateResponse(request, "assessments.html")


@page_router.get("/risk-check", response_class=HTMLResponse)
async def risk_check_page(request: Request):
    return templates.TemplateResponse(request, "risk_check.html")


@page_router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html")


@page_router.get("/blacklist", response_class=HTMLResponse)
async def blacklist_page(request: Request):
    return templates.TemplateResponse(request, "blacklist.html")


@page_router.get("/model", response_class=HTMLResponse)
async def model_report_page(request: Request):
    """模型报告页: 读 xgb_metrics.json 展示 val_auc/特征重要性/假收敛检查."""
    metrics = _load_model_metrics()
    return templates.TemplateResponse(request, "model_report.html", {
        "metrics": metrics or None,
        # 页面 JS 需要原始 JSON (Chart.js 条形图)
        "metrics_json": json.dumps(metrics, ensure_ascii=False) if metrics else "{}",
    })
