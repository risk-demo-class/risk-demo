"""
旅游风控系统 - ORM 模型总入口 (re-export hub)
包含 8 张业务表 + 9 张风控表的 SQLAlchemy 2.x 映射
"""

# 业务表 (8 张, 旅游版)
from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    OrderRefund,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)

# 风控表 (9 张, 完全复用电商基线结构, 仅 ENUM 扩展)
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
    "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
    "BookingHotel", "BookingFlight", "OrderRefund", "BlacklistExtra",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


# ============================================================
# Demo: 列出 17 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 17 张表 (8 业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
        "BookingHotel", "BookingFlight", "OrderRefund", "BlacklistExtra",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
    ]
    print(f"\n[1] 业务表 ({len(business_models)} 张):")
    for i, name in enumerate(business_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 风控表 ({len(risk_models)} 张):")
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
