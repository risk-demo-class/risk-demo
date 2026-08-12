"""银行风控 API 请求与响应模型。"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

BankEventType = Literal["信用卡", "贷款", "转账", "登录"]
RuleEventType = Literal["信用卡", "贷款", "转账", "登录", "通用"]
RuleCategory = Literal["转账欺诈", "信用卡风险", "信贷风险", "账户安全", "设备风险", "IP风险"]
BlacklistType = Literal["用户", "设备指纹", "IP", "银行卡号", "身份证号"]


class RiskCheckRequest(BaseModel):
    """核心契约保持四字段：事件类型、业务ID、客户ID、可选快照。"""
    event_type: BankEventType
    source_id: str = Field(min_length=1, max_length=50, description="交易/贷款/登录业务ID")
    user_id: str = Field(min_length=1, max_length=50)
    event_data: Optional[dict[str, Any]] = None


class RuleHitInfo(BaseModel):
    rule_id: str
    rule_name: str
    rule_category: str
    risk_level: str
    risk_score: int
    action: str
    description: Optional[str] = None


class RiskCheckResponse(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    features: dict[str, Any] = Field(default_factory=dict)
    create_time: datetime
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    blocked_by: Optional[str] = None
    message: Optional[str] = None


class RuleCreate(BaseModel):
    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: RuleCategory
    event_type: RuleEventType = "通用"
    rule_condition: dict[str, Any]
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    rule_category: Optional[RuleCategory] = None
    event_type: Optional[RuleEventType] = None
    rule_condition: Optional[dict[str, Any]] = None
    risk_level: Optional[Literal["低", "中", "高", "极高"]] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action: Optional[Literal["通过", "标记", "人工审核", "拒绝"]] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class RuleResponse(BaseModel):
    rule_id: str
    rule_name: str
    rule_category: str
    event_type: str
    rule_condition: Any
    risk_level: str
    risk_score: int
    action: str
    is_enabled: int
    priority: int
    description: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class RuleListResponse(BaseModel):
    items: list[RuleResponse]
    total: int
    page: int
    page_size: int


class AssessmentItem(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    event_type: str
    event_source_id: str = ""
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    create_time: datetime


class AssessmentListResponse(BaseModel):
    items: list[AssessmentItem]
    total: int
    page: int
    page_size: int


class AssessmentDetailResponse(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    event_type: str
    event_source_id: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    create_time: datetime
    event_data: Optional[str] = None


class BlacklistCreate(BaseModel):
    blacklist_type: BlacklistType
    blacklist_value: str = Field(min_length=1, max_length=200)
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None


class BlacklistResponse(BaseModel):
    blacklist_id: int
    blacklist_type: str
    blacklist_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None
    create_time: Optional[datetime] = None


class BlacklistListResponse(BaseModel):
    items: list[BlacklistResponse]
    total: int
    page: int
    page_size: int


class CaseReviewRequest(BaseModel):
    decision: Literal["已通过", "已拒绝", "已关闭"]
    reviewer: str
    review_comment: Optional[str] = None
    add_to_blacklist: bool = False
    blacklist_expire_hours: Optional[int] = None


class CaseItem(BaseModel):
    case_id: str
    assessment_id: str
    user_id: str
    case_status: str
    case_category: Optional[str] = None
    final_score: Optional[int] = None
    risk_level: Optional[str] = None
    create_time: Optional[datetime] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None


class CaseListResponse(BaseModel):
    items: list[CaseItem]
    total: int
    page: int
    page_size: int


class CaseDetailResponse(BaseModel):
    case_id: str
    assessment_id: str
    user_id: str
    case_status: str
    case_category: Optional[str] = None
    risk_detail: Any = None
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    final_score: Optional[int] = None
    risk_level: Optional[str] = None
    decision: Optional[str] = None
    triggered_rules: list[RuleHitInfo] = Field(default_factory=list)
    user_profile: Optional[dict[str, Any]] = None
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None


class CaseStatistics(BaseModel):
    total: int = 0
    pending: int = 0
    reviewing: int = 0
    approved: int = 0
    rejected: int = 0
    closed: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)


class UserProfileResponse(BaseModel):
    """对外使用银行术语；底层核心表兼容列由 service 映射。"""
    user_id: str
    risk_score: int = 0
    risk_level: str = "低"
    transaction_count_30d: int = 0
    loan_application_count_30d: int = 0
    high_risk_rate: float = 0
    avg_transaction_amount_30d: float = 0
    device_count_30d: int = 0
    failed_login_count_24h: int = 0
    assessment_count: int = 0
    last_assessment_time: Optional[datetime] = None
    profile_data: Any = None


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
