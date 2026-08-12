"""SQLAlchemy ORM 模型总入口。

集中导出 7 张教育业务表和 9 张受保护的风控核心表。业务服务、特征工程
和脚本统一从本模块导入模型，避免依赖具体模型文件的内部组织。
"""

from app.models_business import (
    BUSINESS_MODELS,
    BlacklistExtra,
    Course,
    LearningProgress,
    LiveReward,
    OrderInfo,
    RefundRequest,
    UserInfo,
)
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


RISK_MODELS = (
    RiskRule,
    RiskEvent,
    RiskFeature,
    RiskAssessment,
    RiskCase,
    RiskBlacklist,
    RiskUserProfile,
    RiskActionLog,
    RiskAlert,
)


__all__ = [
    "UserInfo",
    "Course",
    "OrderInfo",
    "LearningProgress",
    "RefundRequest",
    "LiveReward",
    "BlacklistExtra",
    "RiskRule",
    "RiskEvent",
    "RiskFeature",
    "RiskAssessment",
    "RiskCase",
    "RiskBlacklist",
    "RiskUserProfile",
    "RiskActionLog",
    "RiskAlert",
    "BUSINESS_MODELS",
    "RISK_MODELS",
]


if __name__ == "__main__":
    from app.database import Base

    print("=" * 68)
    print("教育行业 AI 风控系统 ORM 模型总览")
    print("=" * 68)

    for title, models in (("教育业务表", BUSINESS_MODELS), ("风控核心表", RISK_MODELS)):
        print(f"\n{title}（{len(models)} 张）:")
        for index, model in enumerate(models, 1):
            columns = list(model.__table__.columns)
            primary_keys = list(model.__table__.primary_key.columns.keys())
            print(
                f"  {index:>2}. {model.__name__:<24} "
                f"table={model.__tablename__:<22} fields={len(columns):>2} PK={primary_keys}"
            )

    print(f"\nBase.metadata 注册表总数: {len(Base.metadata.tables)}")
