"""
物流行业风控系统 - ORM 模型总入口 (re-export hub)
包含 物流业务表 + 风控核心表
"""

# 业务表 (物流行业)

from app.models_business import (
    Address,
    LogisticsStatusUpdate,
    Shipment,
    ShipmentComplaint,
    ShipmentItem,
    UserInfo,
)

# 风控表 (7 个核心 + 2 系统)
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
    "UserInfo", "Address", "Shipment", "ShipmentItem",
    "LogisticsStatusUpdate", "ShipmentComplaint",

    # 风控表
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]
