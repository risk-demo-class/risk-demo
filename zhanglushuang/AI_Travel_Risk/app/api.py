"""API 路由汇总入口."""

from fastapi import APIRouter

from app.routers import (
    agent,
    alert,
    assessment,
    blacklist,
    case,
    dashboard,
    pages,
    profile,
    risk,
    rule,
)

api_router = APIRouter()
api_router.include_router(risk.router)
api_router.include_router(rule.router)
api_router.include_router(assessment.router)
api_router.include_router(case.router)
api_router.include_router(blacklist.router)
api_router.include_router(profile.router)
api_router.include_router(dashboard.router)
api_router.include_router(alert.router)
api_router.include_router(agent.router)
api_router.include_router(pages.router)
