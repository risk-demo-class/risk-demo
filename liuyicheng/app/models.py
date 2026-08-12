"""银行风控 ORM 总入口：8 张银行业务表 + 9 张复用风控表。"""
from app.models_business import (
    BankCard,
    BankTransaction,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
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
    "UserInfo", "BankCard", "BankTransaction", "LoanApplication",
    "LoginLog", "DeviceFingerprint", "IpGeoLocation", "BlacklistExtra",
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile", "RiskActionLog", "RiskAlert",
]


if __name__ == "__main__":
    from app.database import Base

    business = [
        UserInfo, BankCard, BankTransaction, LoanApplication,
        LoginLog, DeviceFingerprint, IpGeoLocation, BlacklistExtra,
    ]
    risk = [
        RiskRule, RiskEvent, RiskFeature, RiskAssessment, RiskCase,
        RiskBlacklist, RiskUserProfile, RiskActionLog, RiskAlert,
    ]
    print(f"银行业务表: {len(business)}")
    print(f"复用风控表: {len(risk)}")
    print(f"metadata 总表数: {len(Base.metadata.tables)}")
