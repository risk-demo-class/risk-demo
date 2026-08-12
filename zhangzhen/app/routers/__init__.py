"""FastAPI 路由包。"""

from app.routers.agent import router as agent_router
from app.routers.assessment import router as assessment_router
from app.routers.blacklist import router as blacklist_router
from app.routers.case import router as case_router
from app.routers.dashboard import router as dashboard_router
from app.routers.health import router as health_router
from app.routers.pages import router as page_router
from app.routers.profile import router as profile_router
from app.routers.risk import router as risk_router
from app.routers.rule import router as rule_router

__all__ = [
    "agent_router",
    "assessment_router",
    "blacklist_router",
    "case_router",
    "dashboard_router",
    "health_router",
    "page_router",
    "profile_router",
    "risk_router",
    "rule_router",
]
