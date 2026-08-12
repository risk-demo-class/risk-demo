"""
银行风控系统 - ORM 模型总入口 (re-export hub)
包含 8 张银行业务表 + 9 张风控表的 SQLAlchemy 2.x 映射
"""

# 业务表 (8 个, 银行场景: 信用卡/贷款/转账/登录)
from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)

# 风控表 (9 个, 字段结构与电商版一致, 枚举值域银行化)
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
    "UserInfo", "BankCard", "Transaction", "LoanApplication",
    "LoginLog", "DeviceFingerprint", "IpGeoLocation", "BlacklistExtra",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]

# 业务实体表名常量 (validator / event / gen 脚本统一引用, 避免硬编码)
# 表名 → ORM 模型 (event_type 校验映射)
EVENT_SOURCE_TABLES = {
    "转账": "transaction",
    "登录": "login_log",
    "贷款申请": "loan_application",
    "信用卡": "bank_card",
}


# ============================================================
# Demo: 列出 17 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 17 张表 (8 业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "BankCard", "Transaction", "LoanApplication",
        "LoginLog", "DeviceFingerprint", "IpGeoLocation", "BlacklistExtra",
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

    # Base.metadata 验证
    from app.database import Base
    total_tables = len(Base.metadata.tables)
    print(f"\n[3] Base.metadata 已注册表数: {total_tables} 张")

    print("\n" + "=" * 60)
    print("结论: 17 张表 1 个导入点 (app.models), service/router 只 from app.models import X")
