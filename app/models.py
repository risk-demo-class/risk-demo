"""
医疗风控系统 - ORM 模型总入口 (re-export hub)
包含 8 张医疗业务表 + 9 张风控表的 SQLAlchemy 2.x 映射
"""

# 医疗业务表 (8 个)
from app.models_business import (
    Appointment,
    BlacklistExtra,
    Doctor,
    DrugOrder,
    Hospital,
    InsuranceClaim,
    Prescription,
    UserInfo,
)

# 风控表 (9 个, 跟电商版完全复用)
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
    # 医疗业务表 (8)
    "UserInfo", "Hospital", "Doctor", "Appointment",
    "Prescription", "InsuranceClaim", "DrugOrder", "BlacklistExtra",
    # 风控表 (9, 完全复用)
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
    print("ORM 模型总览 — 17 张表 (8 医疗业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "Hospital", "Doctor", "Appointment",
        "Prescription", "InsuranceClaim", "DrugOrder", "BlacklistExtra",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
    ]
    print(f"\n[1] 医疗业务表 ({len(business_models)} 张):")
    for i, name in enumerate(business_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 风控表 ({len(risk_models)} 张, 跟电商版完全复用):")
    for i, name in enumerate(risk_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    # Base.metadata 验证
    from app.database import Base
    total_tables = len(Base.metadata.tables)
    print(f"\n[3] Base.metadata 已注册表数: {total_tables} 张")
    print(f"     (Base.metadata 是 SQLAlchemy 自动建表的源, init_db.py 用它 DDL)")

    print("\n" + "=" * 60)
    print("结论: 17 张表 1 个导入点 (app.models), service/router 只 from app.models import X")
