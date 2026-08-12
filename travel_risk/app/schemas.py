"""Pydantic 请求/响应模型: API 端点的数据校验和序列化"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 风控检查
# ============================================================

EventType = Literal["注册", "下单", "支付", "退改申请", "理赔申请", "投诉", "通用"]
RuleCategory = Literal["下单欺诈", "支付风险", "账户风险", "退改滥用", "出行人风险", "供应商风险", "综合风险"]
RiskLevel = Literal["低", "中", "高", "极高"]
Action = Literal["通过", "标记", "人工审核", "拒绝"]
BlacklistType = Literal["用户", "手机号", "设备"]


class RiskCheckRequest(BaseModel):
    """风险检查请求

    最少提供 用户ID / 业务ID / 设备ID 之一即可检查:
      - 只给 user_id    → 通用用户级检查 (source_id 自动取 user_id)
      - 只给 device_id  → 反查最近绑定用户, 通用检查
      - 只给 source_id  → 自动识别业务类型并补全 user_id/event_type
    """
    event_type: Optional[EventType] = None
    source_id: Optional[str] = Field(default=None, description="业务ID (booking_id / payment_id / refund_id / claim_id / complaint_id / user_id)")
    user_id: Optional[str] = None
    booking_id: Optional[str] = None
    device_id: Optional[str] = None
    event_data: Optional[dict] = None


class RuleHitInfo(BaseModel):
    """规则命中信息"""
    rule_id: str
    rule_name: str
    rule_category: str
    risk_level: str
    risk_score: int
    action: str
    description: Optional[str] = None


class RiskCheckResponse(BaseModel):
    """风险检查响应"""
    assessment_id: str
    event_id: str
    user_id: str
    event_type: Optional[str] = None
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    features: dict[str, Any] = {}
    create_time: datetime
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    blocked_by: Optional[str] = None
    message: Optional[str] = None


# ============================================================
# 规则管理
# ============================================================

class RuleCreate(BaseModel):
    """创建规则请求"""
    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: RuleCategory
    event_type: Literal["注册", "下单", "支付", "退改申请", "理赔申请", "投诉", "通用"] = "通用"
    rule_condition: dict
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    action: Action
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求 (所有字段可选)"""
    rule_name: Optional[str] = None
    rule_category: Optional[RuleCategory] = None
    event_type: Optional[Literal["注册", "下单", "支付", "退改申请", "理赔申请", "投诉", "通用"]] = None
    rule_condition: Optional[dict] = None
    risk_level: Optional[RiskLevel] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action: Optional[Action] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class RuleResponse(BaseModel):
    """规则响应"""
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
    """规则列表响应 (分页模式)"""
    items: list[RuleResponse]
    total: int
    page: int
    page_size: int


# ============================================================
# 评估历史
# ============================================================

class AssessmentItem(BaseModel):
    """评估列表条目 (1 行)"""
    assessment_id: str
    event_id: str
    user_id: str
    event_type: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    create_time: datetime


class AssessmentListResponse(BaseModel):
    """评估列表响应"""
    items: list[AssessmentItem]
    total: int
    page: int
    page_size: int


class AssessmentDetailResponse(BaseModel):
    """评估详情 (含命中的规则 + ML 评分)"""
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
    features: dict[str, Any] = {}


# ============================================================
# 黑名单
# ============================================================

class BlacklistCreate(BaseModel):
    """添加黑名单请求"""
    blacklist_type: BlacklistType
    blacklist_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None


class BlacklistResponse(BaseModel):
    """黑名单响应"""
    blacklist_id: int
    blacklist_type: str
    blacklist_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None
    create_time: Optional[datetime] = None


class BlacklistListResponse(BaseModel):
    """黑名单列表响应"""
    items: list[BlacklistResponse]
    total: int
    page: int
    page_size: int


# ============================================================
# 案件管理
# ============================================================

class CaseReviewRequest(BaseModel):
    """案件审核请求"""
    decision: Literal["已通过", "已拒绝", "已关闭"]
    reviewer: str
    review_comment: Optional[str] = None
    add_to_blacklist: bool = False


class CaseItem(BaseModel):
    """案件列表条目"""
    case_id: str
    assessment_id: str
    user_id: str
    case_status: str
    case_category: Optional[str] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class CaseListResponse(BaseModel):
    """案件列表响应"""
    items: list[CaseItem]
    total: int
    page: int
    page_size: int


class CaseDetailResponse(CaseItem):
    """案件详情 (含规则命中明细)"""
    risk_detail: Optional[Any] = None


# ============================================================
# 用户画像
# ============================================================

class ProfileResponse(BaseModel):
    """用户画像响应"""
    user_id: str
    risk_score: int
    risk_level: str
    total_bookings: int
    total_refunds: int
    refund_rate: float
    avg_order_amount: float
    traveler_count: int
    complaint_count: int
    claim_count: int
    assessment_count: int
    last_assessment_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


# ============================================================
# 告警
# ============================================================

class AlertItem(BaseModel):
    """告警条目"""
    alert_id: int
    alert_type: str
    alert_level: str
    alert_title: str
    alert_content: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    status: str
    handler: Optional[str] = None
    create_time: Optional[datetime] = None


class AlertListResponse(BaseModel):
    """告警列表响应"""
    items: list[AlertItem]
    total: int
    page: int
    page_size: int


class AlertResolveRequest(BaseModel):
    """告警处理请求"""
    status: Literal["HANDLING", "RESOLVED", "IGNORED"]
    handler: str
