"""Pydantic 请求/响应模型: API 端点的数据校验和序列化 (物流行业版)"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 风控检查
# ============================================================

class RiskCheckRequest(BaseModel):
    """风险检查请求 (物流行业: 4 种事件类型)"""
    event_type: Literal["寄件下单", "到付签收", "跨境申报", "投诉申诉"]
    source_id: str = Field(description="关联业务ID (shipment_id / declaration_id / record_id)")
    user_id: str
    order_id: Optional[str] = None
    receive_id: Optional[str] = None
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
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    blocked_by: Optional[str] = None


# ============================================================
# 规则管理
# ============================================================

LOGISTICS_RULE_CATEGORY = Literal[
    "寄件欺诈", "实名风险", "危险品瞒报", "跨境异常",
    "到付拒收", "地址风险", "投诉滥用", "综合风险"
]

LOGISTICS_EVENT_TYPE = Literal["寄件下单", "到付签收", "跨境申报", "投诉申诉", "通用"]


class RuleCreate(BaseModel):
    """创建规则请求"""
    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: LOGISTICS_RULE_CATEGORY
    event_type: LOGISTICS_EVENT_TYPE = "通用"
    rule_condition: dict
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求"""
    rule_name: Optional[str] = None
    rule_category: Optional[LOGISTICS_RULE_CATEGORY] = None
    event_type: Optional[LOGISTICS_EVENT_TYPE] = None
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
    """评估列表条目"""
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
    """评估详情"""
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


# ============================================================
# 黑名单 (物流版: 6 种类型)
# ============================================================

BLACKLIST_TYPE = Literal[
    "用户", "身份证号", "手机号", "地址", "运单号", "设备指纹"
]


class BlacklistCreate(BaseModel):
    """添加黑名单请求"""
    blacklist_type: BLACKLIST_TYPE
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
    blacklist_expire_hours: Optional[int] = None


class CaseItem(BaseModel):
    """案件列表项"""
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
    """案件列表响应"""
    items: list[CaseItem]
    total: int
    page: int
    page_size: int


class CaseDetailResponse(BaseModel):
    """案件详情响应"""
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
    triggered_rules: list[RuleHitInfo] = []
    user_profile: Optional[dict] = None
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None


class CaseStatistics(BaseModel):
    """案件统计"""
    total: int = 0
    pending: int = 0
    reviewing: int = 0
    approved: int = 0
    rejected: int = 0
    closed: int = 0
    by_category: dict[str, int] = {}


# ============================================================
# 用户风险画像
# ============================================================

class UserProfileResponse(BaseModel):
    """用户风险画像响应"""
    user_id: str
    risk_score: int = 0
    risk_level: str = "低"
    total_orders: int = 0
    total_refunds: int = 0
    refund_rate: float = 0
    avg_order_amount: float = 0
    address_count: int = 0
    complaint_count: int = 0
    assessment_count: int = 0
    last_assessment_time: Optional[datetime] = None
    profile_data: Any = None


# ============================================================
# AI Agent
# ============================================================

class AgentChatRequest(BaseModel):
    """Agent 对话请求"""
    message: str
    session_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    """Agent 对话响应"""
    reply: str
    session_id: str


if __name__ == "__main__":
    import json

    print("=" * 60)
    print("Pydantic Schema (物流版) — 关键枚举演示")
    print("=" * 60)

    print("\n[1] 事件类型 event_type (4 种 + 通用):")
    print("  寄件下单 | 到付签收 | 跨境申报 | 投诉申诉 | 通用")

    print("\n[2] 规则分类 rule_category (8 种):")
    print("  寄件欺诈 | 实名风险 | 危险品瞒报 | 跨境异常 | 到付拒收 | 地址风险 | 投诉滥用 | 综合风险")

    print("\n[3] 黑名单类型 blacklist_type (6 种):")
    print("  用户 | 身份证号 | 手机号 | 地址 | 运单号 | 设备指纹")

    req = RiskCheckRequest(
        event_type="寄件下单", source_id="SHP001", user_id="U001",
        event_data={"weight_kg": 2.5, "declared_value": 500, "item_category": "日用品"},
    )
    print(f"\n[4] RiskCheckRequest 示例 (寄件下单):\n{req.model_dump_json(indent=2)}")
