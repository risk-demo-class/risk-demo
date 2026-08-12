"""
物流风控系统 - ORM 模型总入口 (re-export hub)
包含 8 张业务表 + 9 张风控表的 SQLAlchemy 2.x 映射
"""

# 业务表 (8 个)
from app.models_business import (
    Address,
    ComplaintRecord,
    CustomsDeclaration,
    ItemCategory,
    Shipment,
    ShipmentItem,
    ShipmentStatus,
    UserInfo,
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
    # 业务表 (8)
    "UserInfo", "Address", "ItemCategory",
    "ShipmentStatus", "Shipment", "ShipmentItem",
    "CustomsDeclaration", "ComplaintRecord",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 17 张表 (8 业务 + 9 风控, 物流版)")
    print("=" * 60)

    business_models = [
        "UserInfo", "ItemCategory", "ShipmentStatus",
        "Address", "Shipment", "ShipmentItem",
        "CustomsDeclaration", "ComplaintRecord",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
    ]
    print(f"\n[1] 物流业务表 ({len(business_models)} 张):")
    for i, name in enumerate(business_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<25} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<25} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 风控表 ({len(risk_models)} 张, 完全复用):")
    for i, name in enumerate(risk_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<25} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<25} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    from app.database import Base
    total_tables = len(Base.metadata.tables)
    print(f"\n[3] Base.metadata 已注册表数: {total_tables} 张")
