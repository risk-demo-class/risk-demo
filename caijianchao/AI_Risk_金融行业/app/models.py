"""
金融风控系统 - ORM 模型总入口 (re-export hub)
包含 14 张业务表 + 9 张风控表的 SQLAlchemy 2.x 映射
"""

# 业务表 (14 个)
from app.models_business import (
    AccountBalanceLog,
    AccountInfo,
    AddressHistory,
    AmlSuspiciousReport,
    Blacklist,
    CreditCardInfo,
    CreditInquiryLog,
    LoanInfo,
    ProductChannel,
    RepaymentRecord,
    TransactionOrder,
    TransactionType,
    UserInfo,
    UserOperationLog,
)

# 风控表 (9 个)
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
    # 业务表 (14)
    "AccountInfo", "UserInfo", "TransactionType", "ProductChannel",
    "TransactionOrder", "AccountBalanceLog",
    "LoanInfo", "RepaymentRecord", "CreditCardInfo", "CreditInquiryLog",
    "Blacklist", "AddressHistory", "UserOperationLog", "AmlSuspiciousReport",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]
