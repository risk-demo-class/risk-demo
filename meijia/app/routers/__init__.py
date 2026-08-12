"""集中导出 FastAPI 路由，main.py 只负责组装应用。"""

from app.routers.assessment import router as assessment_router
from app.routers.agent import router as agent_router
from app.routers.alert import router as alert_router
from app.routers.actionlog import router as actionlog_router
from app.routers.blacklist import router as blacklist_router
from app.routers.case import router as case_router
from app.routers.dashboard import router as dashboard_router
from app.routers.pages import router as page_router
from app.routers.profile import router as profile_router
from app.routers.risk import router as risk_router
from app.routers.rule import router as rule_router
from app.routers.system import router as system_router

ALL_ROUTERS = (
    page_router, system_router, dashboard_router, risk_router, rule_router,
    assessment_router, case_router, blacklist_router, profile_router, agent_router,
    alert_router, actionlog_router,
)

__all__ = ["ALL_ROUTERS"]
