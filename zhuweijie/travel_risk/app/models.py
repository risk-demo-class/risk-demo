"""
旅游风控系统 - ORM 模型总入口 (re-export hub)
包含 7 张旅游业务表 + 9 张风控表 (SQLAlchemy 2.x)
"""
from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    UserInfo,
    VisaApplication,
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
    # 旅游业务表 (7)
    "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
    "BookingFlight", "BookingHotel", "BlacklistExtra",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]