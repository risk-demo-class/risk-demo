"""
ORM 模型总入口 (re-export hub)
业务表: 18 张 (models_business.py)
风控表: 9 张 (models_risk.py)
"""
from app.models_business import (
    BookingDetail,
    BookingInfo,
    BookingStatus,
    BookingTraveler,
    ClaimInfo,
    ComplaintInfo,
    CouponInfo,
    DeviceInfo,
    PaymentInfo,
    ProductCategory,
    ProductInfo,
    RefundChange,
    Region,
    ReviewInfo,
    SupplierInfo,
    TravelerInfo,
    UserDevice,
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
    # 业务表
    "UserInfo", "Region", "ProductCategory", "SupplierInfo", "BookingStatus",
    "DeviceInfo", "ProductInfo", "TravelerInfo", "BookingInfo", "CouponInfo",
    "PaymentInfo", "BookingDetail", "BookingTraveler", "UserDevice",
    "RefundChange", "ComplaintInfo", "ClaimInfo", "ReviewInfo",
    # 风控表
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment", "RiskCase",
    "RiskBlacklist", "RiskUserProfile", "RiskActionLog", "RiskAlert",
]
