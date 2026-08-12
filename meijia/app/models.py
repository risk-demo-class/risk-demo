"""统一导出 ORM，确保导入本模块即可注册全部表。"""

from app.models_business import (  # noqa: F401
    BlacklistExtra,
    Course,
    EducationCredential,
    LearningProgress,
    LiveReward,
    OrderInfo,
    RefundRequest,
    UserDevice,
    UserInfo,
)
from app.models_risk import (  # noqa: F401
    RiskActionLog, RiskAlert, RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskRule,
)

__all__ = [
    "UserInfo", "UserDevice", "Course", "OrderInfo", "LearningProgress",
    "RefundRequest", "BlacklistExtra", "EducationCredential", "LiveReward",
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment", "RiskCase",
    "RiskAlert", "RiskActionLog",
]
