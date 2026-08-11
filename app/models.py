"""
医疗风控系统 - ORM 模型总入口 (re-export hub)
包含 8 张业务表 + 11 张风控表的 SQLAlchemy 2.x 映射
"""

# 业务表 (8 个)
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

# 风控表 (11 个, 2026-08-11 P1 新增 2 张审计/会话表)
from app.models_risk import (
    AgentSession,
    RiskActionLog,
    RiskAlert,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskDataAccessLog,
    RiskEvent,
    RiskFeature,
    RiskRule,
    RiskUserProfile,
)


__all__ = [
    # 业务表 (8)
    "UserInfo", "Hospital", "Doctor",
    "Appointment", "Prescription", "InsuranceClaim", "DrugOrder", "BlacklistExtra",
    # 风控表 (11)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
    "RiskDataAccessLog", "AgentSession",
]


# ============================================================
# Demo: 列出 19 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 19 张表 (8 业务 + 11 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "Hospital", "Doctor",
        "Appointment", "Prescription", "InsuranceClaim", "DrugOrder", "BlacklistExtra",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
        "RiskDataAccessLog", "AgentSession",
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
    print("\n" + "=" * 60)
    print("结论: 19 张表 1 个导入点 (app.models), service/router 只 from app.models import X")
