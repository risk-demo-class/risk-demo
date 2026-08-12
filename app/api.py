"""对齐旧项目：集中导出路由。"""

from app.routers.assessment import assessment_router
from app.routers.blacklist import blacklist_router
from app.routers.case import case_router
from app.routers.dashboard import dashboard_router
from app.routers.pages import page_router
from app.routers.risk import risk_router
from app.routers.rule import rule_router

__all__ = ["page_router", "risk_router", "rule_router", "case_router", "assessment_router", "blacklist_router", "dashboard_router"]
