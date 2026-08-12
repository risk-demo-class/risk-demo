"""ORM 模型统一导出入口。"""

from app.models_business import (
    BUSINESS_MODELS,
    BlacklistExtra,
    Course,
    LearningProgress,
    OrderInfo,
    RefundRequest,
    UserInfo,
)
from app.models_risk import (
    RiskActionLog,
    RiskAlert,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskRule,
    RiskUserProfile,
)

__all__ = [
    "UserInfo",
    "Course",
    "OrderInfo",
    "LearningProgress",
    "RefundRequest",
    "BlacklistExtra",
    "BUSINESS_MODELS",
    "RiskRule",
    "RiskEvent",
    "RiskFeature",
    "RiskAssessment",
    "RiskCase",
    "RiskBlacklist",
    "RiskUserProfile",
    "RiskActionLog",
    "RiskAlert",
]


if __name__ == "__main__":
    from app.database import Base

    print("教育风控 ORM：6 张业务表 + 9 张风控表")
    for model in BUSINESS_MODELS:
        print(f"- {model.__name__:<20} -> {model.__tablename__}")
    print(f"Base.metadata 表数：{len(Base.metadata.tables)}")
