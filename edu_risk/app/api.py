"""
API 聚合层 — 只 re-export 各 router,不写路由。
改 router 不用改 main,所有路由在此汇总。
"""
from app.routers.agent import router as agent_router
from app.routers.blacklist import router as blacklist_router
from app.routers.case import router as case_router
from app.routers.course import router as course_router
from app.routers.dashboard import router as dashboard_router
from app.routers.event import router as event_router
from app.routers.risk import router as risk_router
from app.routers.rule import router as rule_router
from app.routers.setting import router as setting_router
from app.routers.user import router as user_router

__all__ = [
    "risk_router", "rule_router", "case_router", "user_router",
    "dashboard_router", "agent_router", "blacklist_router",
    "event_router", "course_router", "setting_router",
]
