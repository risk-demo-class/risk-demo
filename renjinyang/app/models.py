"""
旅游风控系统 - ORM 模型总入口（re-export hub）
包含 7 张旅游业务表 + 9 张风控核心表的 SQLAlchemy 2.x 映射。
"""

# 旅游业务表（7 个）
from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)

# 风控核心表（9 个，完全复用）
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
    # 旅游业务表（7）
    "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
    "BookingHotel", "BookingFlight", "BlacklistExtra",
    # 风控核心表（9）
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


# ============================================================
# Demo: 列出 16 张表的 ORM 类与字段 — 无需连接数据库
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 16 张表（7 旅游业务 + 9 风控）")
    print("=" * 60)

    business_models = [
        "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
        "BookingHotel", "BookingFlight", "BlacklistExtra",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
    ]

    print(f"\n[1] 旅游业务表（{len(business_models)} 张）:")
    for i, name in enumerate(business_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 风控表（{len(risk_models)} 张）:")
    for i, name in enumerate(risk_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    from app.database import Base

    total_tables = len(Base.metadata.tables)
    print(f"\n[3] Base.metadata 已注册表数: {total_tables} 张")
    print("     （Base.metadata 是 SQLAlchemy 自动建表的数据源）")

    print("\n" + "=" * 60)
    print("结论: 16 张表统一从 app.models 导入")
