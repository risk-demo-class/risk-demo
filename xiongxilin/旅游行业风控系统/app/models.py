"""
旅游行业风控系统 - ORM 模型总入口

包含 10 张旅游业务表 + 9 张风控核心表。
service/router/engine 层统一从 app.models 导入，保持参考项目的导入方式不变。
"""

from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    DestinationRisk,
    OrderInfo,
    PassengerInfo,
    TravelComplaint,
    TravelRefund,
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
    "UserInfo", "DestinationRisk", "OrderInfo", "PassengerInfo",
    "VisaApplication", "BookingHotel", "BookingFlight",
    "TravelRefund", "TravelComplaint", "BlacklistExtra",
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


if __name__ == "__main__":
    from app.database import Base

    print("=" * 60)
    print("旅游行业 ORM 模型总览")
    print("=" * 60)
    for name in __all__:
        cls = globals()[name]
        cols = list(cls.__table__.columns)
        print(f"{name:<24} table={cls.__tablename__:<24} fields={len(cols)}")
    print(f"\nBase.metadata 已注册表数: {len(Base.metadata.tables)}")
