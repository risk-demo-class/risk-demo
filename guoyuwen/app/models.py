"""银行风控 ORM 模型统一导出入口（8 张业务表 + 9 张核心表）。"""

from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
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
    "BankCard",
    "Transaction",
    "LoanApplication",
    "LoginLog",
    "DeviceFingerprint",
    "IpGeoLocation",
    "BlacklistExtra",
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

    business_models = [
        UserInfo,
        BankCard,
        Transaction,
        LoanApplication,
        LoginLog,
        DeviceFingerprint,
        IpGeoLocation,
        BlacklistExtra,
    ]
    risk_models = [
        RiskRule,
        RiskEvent,
        RiskFeature,
        RiskAssessment,
        RiskCase,
        RiskBlacklist,
        RiskUserProfile,
        RiskActionLog,
        RiskAlert,
    ]
    print("银行风控 ORM 模型总览 — 17 张表（8 业务 + 9 核心）")
    for label, models in (("业务表", business_models), ("核心表", risk_models)):
        print(f"\n{label}（{len(models)} 张）")
        for model in models:
            print(f"- {model.__tablename__}: {len(model.__table__.columns)} 字段")
    print(f"\nBase.metadata 已注册 {len(Base.metadata.tables)} 张表")
