"""
旅游风控系统 - FastAPI 路由总入口 (re-export hub)
"""
from app.routers.agent import agent_router
from app.routers.alert import alert_router
from app.routers.assessment import assessment_router
from app.routers.blacklist import blacklist_router
from app.routers.case import case_router
from app.routers.dashboard import dashboard_router
from app.routers.pages import page_router
from app.routers.profile import profile_router
from app.routers.risk import risk_router
from app.routers.rule import rule_router

__all__ = [
    "page_router",
    "risk_router",
    "rule_router",
    "case_router",
    "blacklist_router",
    "profile_router",
    "dashboard_router",
    "agent_router",
    "alert_router",
    "assessment_router",
]
