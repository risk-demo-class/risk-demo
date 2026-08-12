"""页面路由 (Jinja2 模板: 仪表盘 + 风控检查 + Agent 对话)"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async

page_router = APIRouter(tags=["页面"])

# 模板目录: 项目根 / templates
import os
_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@page_router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db_async)):
    """仪表盘首页 (电信风控总览)."""
    from sqlalchemy import func, select
    from app.models_risk import TelecomRiskAssessment, TelecomRiskCase, TelecomRiskRule
    # 4 个统计指标
    rule_count = int((await db.execute(
        select(func.count()).select_from(TelecomRiskRule).where(
            TelecomRiskRule.is_enabled == 1, TelecomRiskRule.deleted_at.is_(None),
        )
    )).scalar() or 0)
    ast_total = int((await db.execute(
        select(func.count()).select_from(TelecomRiskAssessment)
    )).scalar() or 0)
    case_pending = int((await db.execute(
        select(func.count()).select_from(TelecomRiskCase).where(
            TelecomRiskCase.case_status == "待审核"
        )
    )).scalar() or 0)
    high_risk = int((await db.execute(
        select(func.count()).select_from(TelecomRiskAssessment).where(
            TelecomRiskAssessment.risk_level.in_(["高", "极高"])
        )
    )).scalar() or 0)
    return templates.TemplateResponse(request, "index.html", {
        "rule_count": rule_count, "ast_total": ast_total,
        "case_pending": case_pending, "high_risk": high_risk,
    })


@page_router.get("/risk-check", response_class=HTMLResponse)
async def risk_check_page(request: Request):
    """风控检查页 (输入 msisdn + event_type, 调 /api/risk/check)."""
    return templates.TemplateResponse(request, "risk_check.html", {})


@page_router.get("/agent", response_class=HTMLResponse)
async def agent_page(request: Request):
    """AI Agent 对话页 (调 /api/agent/chat, 复用 ai_risk)."""
    return templates.TemplateResponse(request, "agent.html", {})


@page_router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    """规则管理页."""
    return templates.TemplateResponse(request, "rules.html", {})


@page_router.get("/blacklist", response_class=HTMLResponse)
async def blacklist_page(request: Request):
    """黑名单管理页."""
    return templates.TemplateResponse(request, "blacklist.html", {})


@page_router.get("/assessments", response_class=HTMLResponse)
async def assessments_page(request: Request):
    """评估历史页."""
    return templates.TemplateResponse(request, "assessments.html", {})


@page_router.get("/cases", response_class=HTMLResponse)
async def cases_page(request: Request):
    """案件管理页."""
    return templates.TemplateResponse(request, "cases.html", {})
