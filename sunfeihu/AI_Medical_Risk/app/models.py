"""
医疗风控系统 - ORM 模型总入口 (re-export hub)
9 张风控核心表 + 8 张医疗业务表 + 1 张后台用户表
service / router 统一从 app.models import X
"""

# 风控核心表 (9 张, 复用并适配自 AI_Risk)
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

# 医疗业务表 (8 张, P0 新建)
from app.models_business import (
    MedicalDoctor,
    MedicalHospital,
    MedicalInsuranceClaim,
    MedicalPatient,
    MedicalPatientDevice,
    MedicalPrescription,
    MedicalPrescriptionItem,
    MedicalRegistration,
)
from app.models_auth import AppUser


__all__ = [
    # 风控核心表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
    # 医疗业务表 (8)
    "MedicalPatient", "MedicalHospital", "MedicalDoctor",
    "MedicalRegistration", "MedicalPrescription", "MedicalPrescriptionItem",
    "MedicalInsuranceClaim", "MedicalPatientDevice",
    "AppUser",
]


# ============================================================
# Demo: 列出 18 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: uv run python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 18 张表 (9 风控 + 8 医疗 + 1 用户)")
    print("=" * 60)

    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",
    ]
    business_models = [
        "MedicalPatient", "MedicalHospital", "MedicalDoctor",
        "MedicalRegistration", "MedicalPrescription", "MedicalPrescriptionItem",
        "MedicalInsuranceClaim", "MedicalPatientDevice",
    ]
    print(f"\n[1] 风控核心表 ({len(risk_models)} 张):")
    for i, name in enumerate(risk_models, 1):
        cls = globals().get(name)
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<22} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 医疗业务表 ({len(business_models)} 张):")
    for i, name in enumerate(business_models, 1):
        cls = globals().get(name)
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<26} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    from app.database import Base
    print(f"\n[3] Base.metadata 已注册表数: {len(Base.metadata.tables)} 张")
    print("     (init_db.py 用 Base.metadata 生成 DDL, 与 sql/*.sql 保持一致)")
