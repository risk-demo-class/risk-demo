"""
物流风控系统 - ORM 模型总入口 (re-export hub)
包含 9 张风控表 + 12 张物流业务表的 SQLAlchemy 2.x 映射


"""

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

# 物流业务表 (12 个)
from app.models_logistics import (
    LogisticsAbnormalRecord,
    LogisticsAddress,
    LogisticsClaim,
    LogisticsCodSettlement,
    LogisticsComplaint,
    LogisticsCustomerAccount,
    LogisticsCustomsInfo,
    LogisticsEventRecord,
    LogisticsOperator,
    LogisticsRecipient,
    LogisticsSender,
    LogisticsWaybill,
)


__all__ = [
    # 风控表 (9)
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
    "RiskCase", "RiskBlacklist", "RiskUserProfile",
    "RiskActionLog", "RiskAlert",
    # 物流业务表 (12)
    "LogisticsCustomerAccount", "LogisticsSender", "LogisticsRecipient",
    "LogisticsAddress", "LogisticsOperator", "LogisticsWaybill",
    "LogisticsEventRecord", "LogisticsCustomsInfo", "LogisticsCodSettlement",
    "LogisticsClaim", "LogisticsComplaint", "LogisticsAbnormalRecord",
]


# ============================================================
# Demo: 列出 26 张表的所有 ORM 类 + 字段 — 无需连 DB (纯反射)
# 跑法: python app/models.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ORM 模型总览 — 21 张表 (9 风控 + 12 物流业务)")
    print("=" * 60)

    risk_models = [
        "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment",
        "RiskCase", "RiskBlacklist", "RiskUserProfile",
        "RiskActionLog", "RiskAlert",   # P4-L1/L2 系统管理表
    ]
    logistics_models = [
        "LogisticsCustomerAccount", "LogisticsSender", "LogisticsRecipient",
        "LogisticsAddress", "LogisticsOperator", "LogisticsWaybill",
        "LogisticsEventRecord", "LogisticsCustomsInfo", "LogisticsCodSettlement",
        "LogisticsClaim", "LogisticsComplaint", "LogisticsAbnormalRecord",
    ]
    print(f"\n[1] 风控表 ({len(risk_models)} 张):")
    for i, name in enumerate(risk_models, 1):
        cls = globals().get(name)
        if cls is None:
            print(f"  {i:>2}. {name:<30} [NOT FOUND]")
            continue
        cols = list(cls.__table__.columns)
        print(f"  {i:>2}. {name:<30} {len(cols)} 字段  PK={cls.__table__.primary_key.columns.keys()}")

    print(f"\n[2] 物流业务表 ({len(logistics_models)} 张):")
    for i, name in enumerate(logistics_models, 1):
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
    print("结论: 21 张表 1 个导入点 (app.models), service/router 只 from app.models import X")
