"""银行风控系统 - REST 路由包 (移植自 AI_Risk, 银行语义)

拆分 router 文件, 按业务域分组:
  - risk.py         风控检查 (1)
  - rule.py         规则管理 (6)
  - case.py         案件管理 (4)
  - blacklist.py    黑名单管理 (3)
  - profile.py      用户画像 (1)
  - dashboard.py    仪表盘 (1)
  - agent.py        AI Agent (2)
  - alert.py        告警 (3)
  - assessment.py   评估历史 (2)
  - decision.py/features.py/model_eval.py  兼容/辅助接口
"""
from app.routers.risk import risk_router
from app.routers.rule import rule_router
from app.routers.case import case_router
from app.routers.blacklist import blacklist_router
from app.routers.profile import profile_router
from app.routers.dashboard import dashboard_router
from app.routers.agent import agent_router
from app.routers.alert import alert_router
from app.routers.assessment import assessment_router
from app.routers.decision import router as decision_router
from app.routers.features import router as features_router
from app.routers.model_eval import router as model_eval_router

__all__ = [
    "risk_router", "rule_router", "case_router", "blacklist_router", "profile_router",
    "dashboard_router", "agent_router", "alert_router", "assessment_router",
    "decision_router", "features_router", "model_eval_router",
]
