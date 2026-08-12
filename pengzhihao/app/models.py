"""ORM 模型总入口：5 张物流业务表 + 9 张风控核心表。"""

from app.models_business import (
    Address,
    BlacklistExtra,
    OrderInfo,
    ReceiveInfo,
    Shipment,
    ShipmentItem,
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
    "UserInfo", "Address", "Shipment", "ShipmentItem", "BlacklistExtra",
    # 未修改的核心 decision.py 使用的内部兼容名
    "OrderInfo", "ReceiveInfo",
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment", "RiskCase",
    "RiskBlacklist", "RiskUserProfile", "RiskActionLog", "RiskAlert",
]


if __name__ == "__main__":
    from app.database import Base

    print("物流业务表:", ", ".join(
        m.__tablename__ for m in (UserInfo, Address, Shipment, ShipmentItem, BlacklistExtra)
    ))
    print("已注册表数:", len(Base.metadata.tables))
