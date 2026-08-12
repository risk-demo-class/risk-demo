"""
电信风控系统 - FastAPI 路由总入口 (re-export hub)
路由按业务域拆到 router 文件 (app/routers/):

  - page_router        页面 (Jinja2 模板, 仪表盘 + 风控检查 + Agent)
  - risk_router        风控检查 (核心: /api/risk/check)
  - rule_router        规则管理 (CRUD)
  - blacklist_router   黑名单管理
  - assessment_router  评估历史
  - case_router        案件管理
  - agent_router       AI Agent
"""

from app.routers.assessment import assessment_router
from app.routers.agent import agent_router
from app.routers.blacklist import blacklist_router
from app.routers.case import case_router
from app.routers.dashboard import dashboard_router
from app.routers.pages import page_router
from app.routers.risk import risk_router
from app.routers.rule import rule_router


__all__ = [
    "page_router",
    "dashboard_router",
    "risk_router",
    "rule_router",
    "blacklist_router",
    "assessment_router",
    "case_router",
    "agent_router",
]
