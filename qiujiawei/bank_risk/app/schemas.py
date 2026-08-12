"""Pydantic 请求/响应模型: 银行风控 API 端点的数据校验和序列化"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 风控检查
# ============================================================

class RiskCheckRequest(BaseModel):
    """风险检查请求"""
    event_type: Literal["信用卡", "贷款", "转账", "登录"]
    source_id: str = Field(description="关联业务ID (txn_id / loan_id / login_id)")
    user_id: str
    card_id: Optional[str] = None
    device_id: Optional[str] = None
    ip: Optional[str] = None
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
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    features: dict[str, Any] = {}
    create_time: datetime
    # ML 评分: None = 模型未加载
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    # 被哪种黑名单撞了: None=没撞黑, "user"/"card"/"device"/"ip"/"id_card" 五选一.
    # 撞黑时 decision="拒绝" 但不走 7 步决策, 用此字段区分"业务拒绝" vs "黑名单拒绝"
    blocked_by: Optional[str] = None


# ============================================================
# 规则管理
# ============================================================

class RuleCreate(BaseModel):
    """创建规则请求"""
    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: Literal["信用卡欺诈", "贷款风险", "转账风险", "登录风险", "账户风险", "设备风险"]
    event_type: Literal["信用卡", "贷款", "转账", "登录", "通用"] = "通用"
    rule_condition: dict
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求 (所有字段可选)"""
    rule_name: Optional[str] = None
    rule_category: Optional[Literal["信用卡欺诈", "贷款风险", "转账风险", "登录风险", "账户风险", "设备风险"]] = None
    event_type: Optional[Literal["信用卡", "贷款", "转账", "登录", "通用"]] = None
    rule_condition: Optional[dict] = None
    risk_level: Optional[Literal["低", "中", "高", "极高"]] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action: Optional[Literal["通过", "标记", "人工审核", "拒绝"]] = None
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
    """规则列表响应"""
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


# ============================================================
# 黑名单
# ============================================================

class BlacklistCreate(BaseModel):
    """添加黑名单请求"""
    blacklist_type: Literal["user", "device", "ip", "card", "id_card"]
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

class CaseStatusUpdate(BaseModel):
    """案件状态更新请求"""
    case_status: Literal["待审核", "审核中", "已通过", "已拒绝", "已关闭"]
    operator: str = "admin"
    review_comment: Optional[str] = None


class CaseResponse(BaseModel):
    """案件响应"""
    case_id: str
    assessment_id: str
    user_id: str
    case_status: str
    case_category: Optional[str] = None
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None


class CaseListResponse(BaseModel):
    """案件列表响应"""
    items: list[CaseResponse]
    total: int
    page: int
    page_size: int


# ============================================================
# 仪表盘统计
# ============================================================

class DashboardResponse(BaseModel):
    """仪表盘统计响应"""
    total_assessments: int = 0
    total_cases: int = 0
    pending_cases: int = 0
    total_blacklists: int = 0
    total_rules: int = 0
    decision_distribution: dict[str, int] = {}
    event_type_distribution: dict[str, int] = {}
    risk_level_distribution: dict[str, int] = {}


# ============================================================
# 告警
# ============================================================

class AlertResponse(BaseModel):
    """告警响应"""
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
    resolve_time: Optional[datetime] = None


class AlertListResponse(BaseModel):
    """告警列表响应"""
    items: list[AlertResponse]
    total: int
    page: int
    page_size: int
