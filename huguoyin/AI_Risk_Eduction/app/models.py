"""
电商风控系统 - ORM 模型总入口 (re-export hub)
包含电商基线业务表、教育行业业务表、风控表的 SQLAlchemy 2.x 映射


"""

# 业务表 (17 个)
from app.models_business import (
    EduCertificateVerification,
    EduComplaint,
    EduContract,
    EduCourse,
    EduDeviceBinding,
    EduEnrollment,
    EduInstitution,
    EduInstitutionAccountChange,
    EduLearningProgress,
    EduLesson,
    EduLiveReward,
    EduPayment,
    EduRefundRequest,
    EduTeacher,
    EduUserInfo,
    Logistics,
    LogisticsCompany,
    LogisticsComplaint,
    LogisticsComplaintsRecord,
    OrderDetail,
    OrderInfo,
    OrderLogistics,
    OrderStatus,
    Postsale,
    PostsaleLogistics,
    PostsaleReason,
    PostsaleStatus,
    ProductCategory,
    ReceiveInfo,
    Region,
    SkuInfo,
    UserInfo,
)

# 风控表 (7 个)
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
    # 业务表 (17)
    "UserInfo", "Region", "ProductCategory", "SkuInfo",
    "OrderStatus", "OrderInfo", "OrderDetail",
    "Logistics", "OrderLogistics", "LogisticsCompany",
    "LogisticsComplaint", "LogisticsComplaintsRecord",
    "PostsaleStatus", "PostsaleReason", "Postsale", "PostsaleLogistics",
    "ReceiveInfo",
    # 教育行业业务表 (15)
    "EduInstitution", "EduUserInfo", "EduTeacher", "EduCourse",
    "EduEnrollment", "EduContract", "EduPayment", "EduLesson",
    "EduLearningProgress", "EduRefundRequest", "EduComplaint",
    "EduCertificateVerification", "EduLiveReward", "EduDeviceBinding",
    "EduInstitutionAccountChange",
    # 风控表 (9 = 7 业务 + 2 系统管理, P4 新增)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


# ============================================================
# Demo: 列出 26 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 41 张表 (17 电商业务 + 15 教育业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "Region", "ProductCategory", "OrderStatus",
        "LogisticsCompany", "PostsaleStatus", "PostsaleReason",
        "ReceiveInfo", "SkuInfo", "OrderInfo", "OrderDetail",
        "Logistics", "OrderLogistics", "LogisticsComplaint",
        "LogisticsComplaintsRecord", "Postsale", "PostsaleLogistics",
    ]
    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",   # P4-L1/L2 系统管理表
    ]
    education_models = [
        "EduInstitution", "EduUserInfo", "EduTeacher", "EduCourse",
        "EduEnrollment", "EduContract", "EduPayment", "EduLesson",
        "EduLearningProgress", "EduRefundRequest", "EduComplaint",
        "EduCertificateVerification", "EduLiveReward", "EduDeviceBinding",
        "EduInstitutionAccountChange",
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

    print(f"\n[3] 教育业务表 ({len(education_models)} 张):")
    for i, name in enumerate(education_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    # Base.metadata 验证
    from app.database import Base
    total_tables = len(Base.metadata.tables)
    print(f"\n[4] Base.metadata 已注册表数: {total_tables} 张")
    print(f"     (Base.metadata 是 SQLAlchemy 自动建表的源, init_db.py 用它 DDL)")

    print("\n" + "=" * 60)
    print("结论: 业务表和风控表共用 1 个导入点 (app.models), service/router 只 from app.models import X")
