"""HTTP 请求与响应契约。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Decision, EventType, RiskLevel, RuleEventType
from app.models_risk import BlacklistType, CaseStatus, RuleCategory


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    environment: str
    business_table_count: int
    risk_table_count: int
    registered_table_count: int


class ReadinessResponse(ApiModel):
    status: Literal["ready"]
    database: Literal["available"]


class RiskCheckRequest(ApiModel):
    """一次风险检查的稳定四字段契约。"""

    event_type: EventType
    source_id: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=50)
    event_data: dict[str, object] = Field(default_factory=dict)

    @field_validator("source_id", "user_id")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标识不能为空")
        return value


class TriggeredRule(ApiModel):
    rule_id: str
    rule_name: str
    risk_level: RiskLevel
    risk_score: int
    action: Decision
    condition: dict[str, object]
    actual_values: dict[str, float]


class RiskCheckResponse(ApiModel):
    """正常决策和黑名单短路共用的响应。"""

    assessment_id: str | None = None
    event_id: str | None = None
    user_id: str
    final_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    decision: Decision
    rule_count: int = Field(default=0, ge=0)
    triggered_rules: list[TriggeredRule] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    ml_score: float | None = Field(default=None, ge=0, le=1)
    ml_decision: Decision | None = None
    message: str | None = None
    blocked_by: str | None = None
    create_time: datetime


class RuleCreate(ApiModel):
    rule_id: str = Field(min_length=1, max_length=50)
    rule_name: str = Field(min_length=1, max_length=100)
    rule_category: RuleCategory
    event_type: RuleEventType = RuleEventType.COMMON
    rule_condition: dict[str, Any]
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    action: Decision
    is_enabled: bool = True
    priority: int = Field(default=0, ge=0, le=999)
    description: str | None = Field(default=None, max_length=1000)


class RuleUpdate(ApiModel):
    rule_name: str | None = Field(default=None, min_length=1, max_length=100)
    rule_category: RuleCategory | None = None
    event_type: RuleEventType | None = None
    rule_condition: dict[str, Any] | None = None
    risk_level: RiskLevel | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    action: Decision | None = None
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=999)
    description: str | None = Field(default=None, max_length=1000)


class RuleResponse(ApiModel):
    rule_id: str
    rule_name: str
    rule_category: RuleCategory
    event_type: RuleEventType
    rule_condition: dict[str, Any]
    risk_level: RiskLevel
    risk_score: int
    action: Decision
    is_enabled: bool
    priority: int
    description: str | None
    create_time: datetime
    update_time: datetime


class RuleListResponse(ApiModel):
    items: list[RuleResponse]
    total: int
    page: int
    page_size: int


class CaseItem(ApiModel):
    case_id: str
    assessment_id: str
    user_id: str
    case_status: CaseStatus
    case_category: str | None
    source_id: str | None
    event_type: EventType | None
    final_score: int
    risk_level: RiskLevel
    decision: Decision
    rule_count: int
    reviewer: str | None
    create_time: datetime
    update_time: datetime


class CaseListResponse(ApiModel):
    items: list[CaseItem]
    total: int
    page: int
    page_size: int


class CaseStatistics(ApiModel):
    total: int
    pending: int
    reviewing: int
    approved: int
    rejected: int
    closed: int


class CaseDetailResponse(CaseItem):
    risk_detail: dict[str, Any] | None
    review_comment: str | None
    review_time: datetime | None
    triggered_rules: list[dict[str, Any]]
    features: dict[str, float]
    ml_score: float | None
    ml_decision: str | None
    event_data: dict[str, Any] | None


class CaseReviewRequest(ApiModel):
    new_status: CaseStatus
    reviewer: str = Field(min_length=1, max_length=50)
    review_comment: str = Field(min_length=1, max_length=1000)
    add_to_blacklist: bool = False
    blacklist_type: BlacklistType = BlacklistType.USER
    blacklist_value: str | None = Field(default=None, max_length=200)
    blacklist_expire_time: datetime | None = None


class AssessmentItem(ApiModel):
    assessment_id: str
    event_id: str
    user_id: str
    event_type: EventType
    event_source_id: str
    final_score: int
    risk_level: RiskLevel
    decision: Decision
    rule_count: int
    ml_score: float | None
    ml_decision: str | None
    create_time: datetime


class AssessmentListResponse(ApiModel):
    items: list[AssessmentItem]
    total: int
    page: int
    page_size: int


class AssessmentDetailResponse(AssessmentItem):
    triggered_rules: list[dict[str, Any]]
    features: dict[str, float]
    event_data: dict[str, Any] | None


class BlacklistCreate(ApiModel):
    blacklist_type: BlacklistType
    blacklist_value: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    expire_time: datetime | None = None
    operator: str = Field(default="admin", min_length=1, max_length=50)

    @field_validator("blacklist_value")
    @classmethod
    def strip_blacklist_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("黑名单值不能为空")
        return value


class BlacklistResponse(ApiModel):
    blacklist_id: int
    blacklist_type: BlacklistType
    blacklist_value_masked: str
    reason: str | None
    expire_time: datetime | None
    create_time: datetime


class BlacklistListResponse(ApiModel):
    items: list[BlacklistResponse]
    total: int
    page: int
    page_size: int


class UserProfileResponse(ApiModel):
    user_id: str
    risk_score: int
    risk_level: RiskLevel
    txn_count_30d: int
    txn_amount_30d: float
    failed_login_count_30d: int
    device_count: int
    high_risk_ip_count_30d: int
    loan_application_count_30d: int
    debt_ratio: float
    assessment_count: int
    last_assessment_time: datetime | None
    profile_data: dict[str, Any] | None
    update_time: datetime


class DashboardOverview(ApiModel):
    today_assessments: int
    today_high_risk: int
    today_rejected: int
    pending_cases: int
    pass_rate: float
    risk_distribution: dict[str, int]
    event_distribution: dict[str, int]
    decision_distribution: dict[str, int]
    trend_7d: list[dict[str, Any]]
    top_rules: list[dict[str, Any]]


class AgentChatRequest(ApiModel):
    message: str = Field(min_length=1, max_length=2000)


class AgentChatResponse(ApiModel):
    reply: str
    model_available: bool
