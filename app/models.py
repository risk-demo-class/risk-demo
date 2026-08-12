"""
物流风控系统 - ORM 模型总入口 (re-export hub)
包含 9 张物流业务表 (7 核心 + 2 支撑) + 9 张风控表的 SQLAlchemy 2.x 映射

【重要约定】sender_id == user_id (寄件人账号即风控主体), 特征查询直接按 user_id 走 parcel 表.
"""
from datetime import datetime

# 业务表 (9 个 = 7 核心 + 2 支撑)
from app.models_business import (
    BlacklistExtra,
    CodTransaction,
    DangerousDeclaration,
    ItemCategory,
    Parcel,
    ReceiverInfo,
    Region,
    SenderInfo,
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
    # 业务表 (9)
    "UserInfo", "SenderInfo", "ReceiverInfo", "Parcel",
    "DangerousDeclaration", "CodTransaction", "BlacklistExtra",
    "Region", "ItemCategory",
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
]


# ============================================================
# Demo: 列出 18 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 18 张表 (9 业务 + 9 风控)")
    print("=" * 60)

    business_models = [
        "UserInfo", "SenderInfo", "ReceiverInfo", "Parcel",
        "DangerousDeclaration", "CodTransaction", "BlacklistExtra",
        "Region", "ItemCategory",
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
    print(f"     (Base.metadata 是 SQLAlchemy 自动建表的源, init_db.py 用它 DDL)")

    print("\n" + "=" * 60)
    print("结论: 18 张表 1 个导入点 (app.models), service/router 只 from app.models import X")
