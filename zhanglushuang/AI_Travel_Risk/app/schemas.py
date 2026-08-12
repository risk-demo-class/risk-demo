"""
Pydantic 请求 / 响应模型.

事件类型与规则分类统一在 schema 层约束, 保持 API 输入可校验.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EVENT_TYPES = Literal["下单", "支付", "退改申请", "签证申请", "拼团报名"]
RULE_CATEGORIES = Literal[
    "订单欺诈",
    "支付风险",
    "账户风险",
    "退改滥用",
    "签证风险",
    "设备风险",
    "跨境风险",
]
BLACKLIST_TYPES = Literal[
    "用户",
    "手机号",
    "护照号",
    "签证号",
    "设备指纹",
    "支付账号",
    "IP",
]
DECISIONS = Literal["通过", "标记", "人工审核", "拒绝"]
RISK_LEVELS = Literal["低", "中", "高", "极高"]


class RiskCheckRequest(BaseModel):
    """风控检查请求."""

    event_type: EVENT_TYPES
    source_id: str = Field(description="关联业务ID: 订单/签证/退改/拼团单ID")
    user_id: str
    order_id: Optional[str] = None
    receive_id: Optional[str] = Field(
        default=None,
        description="复用基线字段, 旅游场景表示联系人/乘客关联ID",
    )
    event_data: Optional[dict] = None


class RuleHitInfo(BaseModel):
    """规则命中信息."""

    rule_id: str
    rule_name: str
    rule_category: str
    risk_level: str
    risk_score: int
    action: str
    description: Optional[str] = None


class RiskCheckResponse(BaseModel):
    """风控检查响应."""

    assessment_id: str
    event_id: str
    user_id: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    features: dict[str, Any] = {}
    ml_score: Optional[float] = None
    ml_probability: Optional[float] = None
    ml_decision: Optional[str] = None
    llm_score: Optional[float] = None
    blocked_by: Optional[str] = None
    create_time: datetime


class RuleCreate(BaseModel):
    """新增规则请求."""

    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: RULE_CATEGORIES
    event_type: Literal["下单", "支付", "退改申请", "签证申请", "拼团报名", "通用"] = "通用"
    rule_condition: dict
    risk_level: RISK_LEVELS
    risk_score: int = Field(ge=0, le=100)
    action: DECISIONS
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求."""

    rule_name: Optional[str] = None
    rule_category: Optional[RULE_CATEGORIES] = None
    event_type: Optional[Literal["下单", "支付", "退改申请", "签证申请", "拼团报名", "通用"]] = None
    rule_condition: Optional[dict] = None
    risk_level: Optional[RISK_LEVELS] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action: Optional[DECISIONS] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class RuleResponse(BaseModel):
    """规则响应."""

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
    """规则列表响应."""

    items: list[RuleResponse]
    total: int
    page: int
    page_size: int


class AssessmentItem(BaseModel):
    """评估列表条目."""

    assessment_id: str
    event_id: str
    user_id: str
    event_type: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    ml_score: Optional[float] = None
    create_time: Optional[datetime] = None


class AssessmentListResponse(BaseModel):
    """评估历史列表."""

    items: list[AssessmentItem]
    total: int
    page: int
    page_size: int


class AssessmentDetailResponse(BaseModel):
    """评估详情."""

    assessment_id: str
    event_id: str
    user_id: str
    event_type: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    rule_results: Any = None
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    create_time: Optional[datetime] = None


class BlacklistCreate(BaseModel):
    """新增黑名单请求."""

    blacklist_type: BLACKLIST_TYPES
    blacklist_value: str
    reason: Optional[str] = None
    expire_hours: Optional[int] = Field(default=None, ge=1, description="过期小时数, NULL=永久")


class BlacklistResponse(BaseModel):
    """黑名单响应."""

    blacklist_id: int
    blacklist_type: str
    blacklist_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None
    create_time: Optional[datetime] = None


class BlacklistListResponse(BaseModel):
    """黑名单列表."""

    items: list[BlacklistResponse]
    total: int
    page: int
    page_size: int


class CaseReviewRequest(BaseModel):
    """案件审核请求."""

    decision: Literal["通过", "拒绝"]
    comment: Optional[str] = None
    reviewer: Optional[str] = None


class CaseItem(BaseModel):
    """案件列表条目."""

    case_id: str
    assessment_id: str
    user_id: str
    case_status: str
    case_category: Optional[str] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None
    create_time: Optional[datetime] = None


class CaseListResponse(BaseModel):
    """案件列表."""

    items: list[CaseItem]
    total: int
    page: int
    page_size: int


class CaseDetailResponse(BaseModel):
    """案件详情."""

    case_id: str
    assessment_id: str
    user_id: str
    case_status: str
    case_category: Optional[str] = None
    risk_detail: Any = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class CaseStatistics(BaseModel):
    """案件统计."""

    total: int = 0
    pending: int = 0
    reviewing: int = 0
    approved: int = 0
    rejected: int = 0
    closed: int = 0


class UserProfileResponse(BaseModel):
    """用户风险画像响应."""

    user_id: str
    risk_score: int
    risk_level: str
    total_orders: int
    total_refunds: int
    refund_rate: float
    avg_order_amount: float
    address_count: int
    complaint_count: int
    assessment_count: int
    last_assessment_time: Optional[datetime] = None
    profile_data: Any = None


class AgentChatRequest(BaseModel):
    """AI Agent 对话请求."""

    message: str
    session_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    """AI Agent 对话响应."""

    session_id: str
    reply: str
