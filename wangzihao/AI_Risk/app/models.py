"""ORM 模型统一导出：6 张制造业业务表 + 9 张核心风控表。"""

from app.models_business import (
    BlacklistExtra,
    CrossRegionReport,
    Dealer,
    Device,
    PurchaseOrder,
    WarrantyClaim,
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


class _PurchaseOrderDecisionCompatibility:
    """供冻结的 decision.py 旧导入名使用，不注册新 ORM 表。"""

    order_id = PurchaseOrder.po_id
    receive_id = PurchaseOrder.ship_to


# Step 4 临时兼容：冻结的 decision.py 仍显式导入 OrderInfo。
# 不加入 __all__，制造业业务模型公开契约仍严格为 6 张表。
OrderInfo = _PurchaseOrderDecisionCompatibility


__all__ = [
    "Dealer",
    "Device",
    "PurchaseOrder",
    "WarrantyClaim",
    "CrossRegionReport",
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
        Dealer,
        Device,
        PurchaseOrder,
        WarrantyClaim,
        CrossRegionReport,
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

    print("=" * 60)
    print("ORM 模型总览 — 15 张表（6 业务 + 9 风控）")
    print("=" * 60)
    for title, models in (("制造业业务表", business_models), ("核心风控表", risk_models)):
        print(f"\n[{title}] {len(models)} 张")
        for model in models:
            table = model.__table__
            print(f"  {table.name:<28} 字段={len(table.columns):>2} PK={list(table.primary_key.columns.keys())}")
    print(f"\nBase.metadata 注册表数: {len(Base.metadata.tables)}")
