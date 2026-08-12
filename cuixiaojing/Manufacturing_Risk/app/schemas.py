"""Pydantic 请求/响应模型: API 端点的数据校验和序列化"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 常量 (跟 DB Enum / 前端下拉框一一对应)
# ============================================================

EVENT_TYPES = ["经销商订货", "保修申请", "售后维修", "串货举报"]
RULE_EVENT_TYPES = EVENT_TYPES + ["通用"]
RULE_CATEGORIES = ["串货风险", "保修滥用", "囤货风险", "维修异常", "资质风险", "综合风险"]
RISK_LEVELS = ["低", "中", "高", "极高"]
DECISIONS = ["通过", "标记", "人工审核", "拒绝"]
BLACKLIST_TYPES = ["经销商ID", "设备SN", "维修工", "用户"]


# ============================================================
# 风控检查
# ============================================================

class RiskCheckRequest(BaseModel):
    """风险检查请求"""
    event_type: Literal["经销商订货", "保修申请", "售后维修", "串货举报"]
    source_id: str = Field(description="关联业务ID (order_id / warranty_id / report_id)")
    user_id: str = Field(description="用户ID (经销商ID / 举报人ID)")
    order_id: Optional[str] = None
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
    # XGBoost 评分: None = 模型未加载
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    # 被哪种黑名单撞了: None=没撞黑, "经销商ID"/"设备SN"/"维修工"/"用户" 四选一
    blocked_by: Optional[str] = None


# ============================================================
# 规则管理
# ============================================================

class RuleCreate(BaseModel):
    """创建规则请求"""
    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: Literal["串货风险", "保修滥用", "囤货风险", "维修异常", "资质风险", "综合风险"]
    event_type: Literal["经销商订货", "保修申请", "售后维修", "串货举报", "通用"] = "通用"
    rule_condition: dict
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求 (所有字段可选)"""
    rule_name: Optional[str] = None
    rule_category: Optional[Literal["串货风险", "保修滥用", "囤货风险", "维修异常", "资质风险", "综合风险"]] = None
    event_type: Optional[Literal["经销商订货", "保修申请", "售后维修", "串货举报", "通用"]] = None
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
    """规则列表响应 ({items, total} 分页模式)"""
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


# ============================================================
# 黑名单
# ============================================================

class BlacklistCreate(BaseModel):
    """添加黑名单请求"""
    blacklist_type: Literal["经销商ID", "设备SN", "维修工", "用户"]
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
    pending: int = 0    # 待审核
    reviewing: int = 0  # 审核中
    approved: int = 0   # 已通过
    rejected: int = 0   # 已拒绝
    closed: int = 0     # 已关闭
    by_category: dict[str, int] = {}


# ============================================================
# 用户风险画像
# ============================================================

class UserProfileResponse(BaseModel):
    """经销商风险画像响应"""
    user_id: str
    risk_score: int = 0
    risk_level: str = "低"
    total_orders: int = 0
    total_amount: float = 0
    avg_order_amount: float = 0
    warranty_count: int = 0
    repair_count: int = 0
    contract_expired: int = 0
    assessment_count: int = 0
    last_assessment_time: Optional[datetime] = None
    profile_data: Any = None


# ============================================================
# AI Agent
# ============================================================

class AgentChatRequest(BaseModel):
    """AI 助手对话请求"""
    message: str
    session_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    """AI 助手对话响应"""
    reply: str
    session_id: str


# ============================================================
# Demo: 演练 3 个典型 schema 的构造 + 序列化 (无需 DB / 服务)
# 跑法: python -m app.schemas
# ============================================================
if __name__ == "__main__":
    import json

    print("=" * 60)
    print("Pydantic Schema 演示 (3 个典型代表)")
    print("=" * 60)

    # 1. RiskCheckRequest — 入口 (前端"风险检查"页触发)
    req = RiskCheckRequest(
        event_type="经销商订货", source_id="ORD001", user_id="D001",
        event_data={"amount": 480000, "product": "工业机械臂"},
    )
    print("\n[1] RiskCheckRequest (入口):")
    print(req.model_dump_json(indent=2))

    # 2. RuleHitInfo + RiskCheckResponse — 7 步流水线返回
    hits = [
        RuleHitInfo(
            rule_id="R005", rule_name="大额经销商囤货",
            rule_category="囤货风险", risk_level="高",
            risk_score=70, action="人工审核",
            description="单笔订单>100万, 疑似囤货/窜货",
        ),
    ]
    resp = RiskCheckResponse(
        assessment_id="ast_demo_xxx", event_id="evt_demo_xxx",
        user_id="D001", final_score=70, risk_level="高", decision="人工审核",
        rule_count=1, triggered_rules=hits,
        features={"order_total_amount": 1200000},
        create_time=datetime.now(),
    )
    print("\n[2] RiskCheckResponse (响应):")
    print(f"  final_score = {resp.final_score} / {resp.risk_level} / {resp.decision}")
    print(f"  rule_count  = {resp.rule_count}, 首条命中 = {resp.triggered_rules[0].rule_name}")

    # 3. 常量清单
    print("\n[3] 常量清单:")
    print(f"  EVENT_TYPES     = {EVENT_TYPES}")
    print(f"  RULE_CATEGORIES = {RULE_CATEGORIES}")
    print(f"  BLACKLIST_TYPES = {BLACKLIST_TYPES}")

    print("\n" + "=" * 60)
    print("总结: schema 覆盖 风控检查 / 规则管理 / 黑名单 / 案件 / 画像 / 评估历史")
