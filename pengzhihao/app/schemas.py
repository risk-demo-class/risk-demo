"""Pydantic 请求/响应模型: API 端点的数据校验和序列化"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# 风控检查
# ============================================================

class RiskCheckRequest(BaseModel):
    """物流风险检查公开契约（严格四字段）。"""
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["寄件受理", "安检验视", "跨境申报", "代收货款"]
    source_id: str = Field(description="运单ID shipment_id")
    user_id: str
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
    # 被哪种物流黑名单撞了；支持核心三类业务标签和四类扩展实体。
    # 撞黑时 decision="拒绝" 但不走 7 步决策, 用此字段区分"业务拒绝" vs "黑名单拒绝"
    blocked_by: Optional[str] = None


# ============================================================
# 规则管理
# ============================================================

class RuleCreate(BaseModel):
    """创建规则请求"""
    rule_id: str = Field(max_length=50)
    rule_name: str = Field(max_length=100)
    rule_category: Literal["寄递实名", "禁限寄安全", "跨境申报", "代收货款", "地址风险", "行为异常"]
    event_type: Literal["寄件受理", "安检验视", "跨境申报", "代收货款", "通用"] = "通用"
    rule_condition: dict
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    priority: int = 0
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求 (所有字段可选)"""
    rule_name: Optional[str] = None
    rule_category: Optional[Literal["寄递实名", "禁限寄安全", "跨境申报", "代收货款", "地址风险", "行为异常"]] = None
    event_type: Optional[Literal["寄件受理", "安检验视", "跨境申报", "代收货款", "通用"]] = None
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
    """规则列表响应 (P4-L4 2026-08-08: 对齐 assessments/cases 的 {items, total} 分页模式)"""
    items: list[RuleResponse]
    total: int
    page: int
    page_size: int




# ============================================================
# 评估历史 (P3-S9 2026-08-08): 案件工作台只看"待办", 已结案 + 全量评估都走这里
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
    # 关联 event 的 event_data (JSON 字符串, 前端可再 parse 展示)
    event_data: Optional[str] = None


# ============================================================
# 黑名单
# ============================================================
class BlacklistCreate(BaseModel):
    """添加黑名单请求"""
    blacklist_type: Literal["寄件人", "收件地址", "联系电话"]
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
    """黑名单列表响应 (P4-L4 2026-08-08: 对齐 assessments/cases 的 {items, total} 分页模式)"""
    items: list[BlacklistResponse]
    total: int
    page: int
    page_size: int


class BlacklistExtraCreate(BaseModel):
    """物流扩展黑名单请求。实名证件应传入证件哈希，不接收明文证件号。"""
    entity_type: Literal["实名证件", "设备指纹", "IP地址", "海关主体"]
    entity_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None


class BlacklistExtraResponse(BaseModel):
    extra_id: int
    entity_type: str
    entity_value: str
    reason: Optional[str] = None
    source: str
    status: str
    expire_time: Optional[datetime] = None
    create_time: datetime


# ============================================================
# 案件管理
# ============================================================

class CaseReviewRequest(BaseModel):
    """案件审核请求"""
    decision: Literal["已通过", "已拒绝", "已关闭"]
    reviewer: str
    review_comment: Optional[str] = None
    add_to_blacklist: bool = False
    # 【P3-M7】黑名单过期时间 (小时). None=永久 (默认, 跟原行为一致);
    # 24/72/168/720 = 临时封禁
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
    # 业务回溯字段 (前端"重做检查"按钮用)
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
    # 关联的评估信息
    final_score: Optional[int] = None
    risk_level: Optional[str] = None
    decision: Optional[str] = None
    triggered_rules: list[RuleHitInfo] = []
    user_profile: Optional[dict] = None
    # 【P4-L4 2026-08-08】ML 评分 (XGBoost 拒绝概率 + 决策, 前端会再 sigmoid 校准成 0-100 风险分)
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    # 业务回溯字段 (重做检查用)
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


# ============================================================
# Demo: 演练 3 个典型 schema 的构造 + 序列化 (无需 DB / 服务)
# 跑法: python app/schemas.py
# ============================================================
if __name__ == "__main__":
    import json
    from datetime import datetime

    print("=" * 60)
    print("Pydantic Schema 演示 (19 个类的 3 个典型代表)")
    print("=" * 60)

    # 1. RiskCheckRequest — 入口 (前端"风险检查"页触发)
    req = RiskCheckRequest(
        event_type="安检验视", source_id="SHP0001", user_id="U_DANGER",
        event_data={"inspection_station": "DEMO-01"},
    )
    print("\n[1] RiskCheckRequest (入口):")
    print(req.model_dump_json(indent=2))

    # 2. RuleHitInfo + RiskCheckResponse — 7 步流水线返回
    hits = [
        RuleHitInfo(
            rule_id="L002", rule_name="疑似危险品瞒报",
            rule_category="禁限寄安全", risk_level="极高",
            risk_score=95, action="拒绝",
            description="验视发现未申报锂电池等禁限寄物品",
        ),
        RuleHitInfo(
            rule_id="L009", rule_name="共享或临时地址",
            rule_category="地址风险", risk_level="高",
            risk_score=65, action="人工审核",
        ),
    ]
    resp = RiskCheckResponse(
        assessment_id="ast_demo_xxx", event_id="evt_demo_xxx",
        user_id="U_DANGER", final_score=95, risk_level="极高", decision="拒绝",
        rule_count=2, triggered_rules=hits,
        features={"user_total_orders": 3, "order_total_amount": 15000},
        create_time=datetime.now(),
        ml_score=0.92, ml_decision="拒绝",
    )
    print("\n[2] RiskCheckResponse (响应, 含 2 条命中规则 + ML 评分):")
    print(f"  final_score    = {resp.final_score}")
    print(f"  risk_level     = {resp.risk_level}")
    print(f"  decision       = {resp.decision}")
    print(f"  rule_count     = {resp.rule_count}")
    print(f"  ml_score       = {resp.ml_score} (P 拒绝)")
    print(f"  ml_decision    = {resp.ml_decision}")
    print(f"  triggered_rules (前 1 条): {resp.triggered_rules[0].rule_name} ({resp.triggered_rules[0].risk_level})")

    # 3. AssessmentDetailResponse (P3-S9) — 评估历史详情
    detail = AssessmentDetailResponse(
        assessment_id="ast_demo_xxx", event_id="evt_demo_xxx",
        user_id="U_DANGER", event_type="安检验视", event_source_id="SHP0001",
        final_score=95, risk_level="极高", decision="拒绝",
        rule_count=2, triggered_rules=hits,
        create_time=datetime.now(),
        ml_score=0.92, ml_decision="拒绝",
        event_data=json.dumps({"inspection_station": "DEMO-01"}, ensure_ascii=False),
    )
    print("\n[3] AssessmentDetailResponse (P3-S9 评估历史详情):")
    print(f"  event_source_id = {detail.event_source_id}")
    print(f"  event_data      = {detail.event_data}")
    print(f"  字段数          = {len(detail.model_dump())} 个")

    print("\n" + "=" * 60)
    print("总结: schema 覆盖运单检查 / 物流规则 / 黑名单 / 案件 / 寄件人画像 / Agent / 评估历史")
