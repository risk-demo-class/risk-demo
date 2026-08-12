"""
旅游风控系统 - ORM 模型总入口 (re-export hub)
包含 7 张行业业务表 + 9 张风控核心表的 SQLAlchemy 2.x 映射

9 张风控核心表 (risk_rule / risk_event / risk_feature / risk_assessment /
risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert)
完全复用基线, 只有枚举值按行业调整 (事件类型/黑名单类型/特征实体类型).
"""

# 行业业务表 (7 张, 全部自研)
from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)

# 风控核心表 (9 张, 复用基线)
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
    # 行业业务表 (7)
    "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
    "BookingFlight", "BookingHotel", "BlacklistExtra",
    # 风控核心表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


# ============================================================
# Demo: 列出 16 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 16 张表 (7 行业业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "OrderInfo", "PassengerInfo", "VisaApplication",
        "BookingFlight", "BookingHotel", "BlacklistExtra",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
    ]
    print(f"\n[1] 行业业务表 ({len(business_models)} 张):")
    for i, name in enumerate(business_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 风控核心表 ({len(risk_models)} 张):")
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
    print("     (Base.metadata 是 SQLAlchemy 自动建表的源)")

    print("\n" + "=" * 60)
    print("结论: 16 张表 1 个导入点 (app.models), service/router 只 from app.models import X")
