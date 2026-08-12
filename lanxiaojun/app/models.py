"""
教育风控系统 - ORM 模型总入口 (re-export hub)
包含 10 张业务表 + 9 张风控表的 SQLAlchemy 2.x 映射
"""
# 业务表 (10 张)
from app.models_business import (
    Complaint,
    Course,
    DeviceFingerprint,
    LearningProgress,
    OrderInfo,
    PaymentAccount,
    RefundRequest,
    StudentProfile,
    TeacherInfo,
    UserInfo,
)

# 风控表 (9 张)
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
    # 业务表 (10)
    "UserInfo", "StudentProfile", "TeacherInfo",
    "Course", "OrderInfo", "LearningProgress",
    "RefundRequest", "Complaint",
    "PaymentAccount", "DeviceFingerprint",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]

if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 19 张表 (10 业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "StudentProfile", "TeacherInfo",
        "Course", "OrderInfo", "LearningProgress",
        "RefundRequest", "Complaint",
        "PaymentAccount", "DeviceFingerprint",
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
    print(f"     (Base.metadata 是 SQLAlchemy 自动建表的源, init_db.py 用它 DDL)")
    print("\n" + "=" * 60)
    print("结论: 19 张表 1 个导入点 (app.models), service/router 只 from app.models import X")