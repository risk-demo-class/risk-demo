"""ORM统一出口：7张物流业务表 + 9张通用风控表。"""
from app.models_business import (
    Address, BlacklistExtra, CustomsDeclaration, DeliveryResult,
    Shipment, ShipmentItem, UserInfo,
)
from app.models_risk import (
    RiskActionLog, RiskAlert, RiskAssessment, RiskBlacklist, RiskCase,
    RiskEvent, RiskFeature, RiskRule, RiskUserProfile,
)

__all__ = [
    "UserInfo", "Address", "Shipment", "ShipmentItem", "CustomsDeclaration",
    "DeliveryResult", "BlacklistExtra",
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment", "RiskCase",
    "RiskBlacklist", "RiskUserProfile", "RiskActionLog", "RiskAlert",
]
