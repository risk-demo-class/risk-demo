"""API 路由枢纽: 所有 router 汇总到这里, scripts/main.py 统一注册"""
from app.routers.agent import agent_router
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
    "assessment_router",
    "agent_router",
]
