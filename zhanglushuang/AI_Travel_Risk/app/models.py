"""
模型汇总入口.

业务代码统一从 app.models 导入模型, 启动时 SQLAlchemy 会注册全部表.
"""

from app.database import Base
from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    DeviceFingerprint,
    GroupBooking,
    HotelPreauthorization,
    OrderInfo,
    PassengerInfo,
    TicketChangeApplication,
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
    "Base",
    "BlacklistExtra",
    "BookingFlight",
    "BookingHotel",
    "DeviceFingerprint",
    "GroupBooking",
    "HotelPreauthorization",
    "OrderInfo",
    "PassengerInfo",
    "RiskActionLog",
    "RiskAlert",
    "RiskAssessment",
    "RiskBlacklist",
    "RiskCase",
    "RiskEvent",
    "RiskFeature",
    "RiskRule",
    "RiskUserProfile",
    "TicketChangeApplication",
    "UserInfo",
    "VisaApplication",
]
