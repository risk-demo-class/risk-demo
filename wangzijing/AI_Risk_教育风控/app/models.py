"""教育风控 ORM 总入口：七张业务表与九张风控核心表。"""

from app.models_business import (
    Course,
    DeviceBinding,
    IdentityVerification,
    LearningProgress,
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
from app.models_system import SysUser

__all__ = [
    "UserInfo",
    "Course",
    "OrderInfo",
    "LearningProgress",
    "RefundRequest",
    "IdentityVerification",
    "DeviceBinding",
    "RiskRule",
    "RiskEvent",
    "RiskFeature",
    "RiskAssessment",
    "RiskCase",
    "RiskBlacklist",
    "RiskUserProfile",
    "RiskActionLog",
    "RiskAlert",
    "SysUser",
]


if __name__ == "__main__":
    from app.database import Base

    print("教育风控 ORM：7 张业务表 + 9 张风控表")
    for table_name in sorted(Base.metadata.tables):
        table = Base.metadata.tables[table_name]
        print(f"- {table_name}: {len(table.columns)} 个字段")
