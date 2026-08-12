"""教育业务表与不变的风控核心表总入口。"""
from app.models_business import Course, Enrollment, LearningProgress, LiveReward, RefundRequest, UserInfo
from app.models_risk import (
    RiskActionLog, RiskAlert, RiskAssessment, RiskBlacklist, RiskCase, RiskEvent,
    RiskFeature, RiskRule, RiskUserProfile,
)

# 兼容旧 Agent 模块的导入名称；教育版业务链路只使用上面的真实教育模型。
OrderInfo = Enrollment
OrderDetail = Enrollment
Postsale = RefundRequest
ReceiveInfo = UserInfo
LogisticsComplaintsRecord = LiveReward
SkuInfo = Course
Logistics = LiveReward
LogisticsCompany = LiveReward
LogisticsComplaint = LiveReward
OrderLogistics = Enrollment
OrderStatus = Enrollment
PostsaleLogistics = RefundRequest
PostsaleReason = RefundRequest
PostsaleStatus = RefundRequest
ProductCategory = Course
Region = UserInfo

__all__ = [
    "UserInfo", "Course", "Enrollment", "LearningProgress", "RefundRequest", "LiveReward",
    "RiskRule", "RiskEvent", "RiskFeature", "RiskAssessment", "RiskCase", "RiskBlacklist",
    "RiskUserProfile", "RiskActionLog", "RiskAlert",
]
