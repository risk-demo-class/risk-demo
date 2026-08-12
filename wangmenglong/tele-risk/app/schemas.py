"""
电信风控系统 - Pydantic 请求/响应模型
======================================
参照 ai_risk/app/schemas.py, 适配电信业务 (msisdn 替代 user_id, 电信事件类型).

覆盖: 风控检查 / 规则管理 / 黑名单 / 案件 / 号卡画像 / Agent / 评估历史
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 风控检查 (核心入口)
# ============================================================

# 电信事件类型 (跟 config.RISK_EVENT_THRESHOLDS 对齐)
TelecomEventType = Literal["开户", "通话", "国际来电", "短信发送", "物联网激活"]


class RiskCheckRequest(BaseModel):
    """风险检查请求 (号卡 msisdn 是核心枢纽)."""
    event_type: TelecomEventType
    source_id: str = Field(description="关联业务ID (业务单号 / CDR ID 等)")
    msisdn: str = Field(description="号卡 (11位手机号)")
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
    """风险检查响应 (7 步流水线返回)."""
    assessment_id: str
    event_id: str
    msisdn: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    features: dict[str, Any] = {}
    create_time: datetime
    # XGBoost 评分: None = 模型未加载 / 撞黑不走决策
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    # 撞黑名单: None=没撞黑, "号卡"/"客户"/"设备"/"渠道" 四选一
    blocked_by: Optional[str] = None
    # 人类可读的拒绝原因 (前端直接显示)
    message: Optional[str] = None


# ============================================================
# 规则管理
# ============================================================

# 电信规则类别 (跟 init_risk_tables.sql 对齐)
TelecomRuleCategory = Literal[
    "通话欺诈", "设备欺诈", "账户风险", "国际来电", "物联网滥用", "渠道异常",
]


class RuleCreate(BaseModel):
    """创建规则请求."""
    rule_id: str = Field(max_length=20)
    rule_name: str = Field(max_length=80)
    rule_category: TelecomRuleCategory
    event_type: Literal["开户", "通话", "国际来电", "短信发送", "物联网激活", "通用"] = "通用"
    rule_condition: dict
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝", "关停号码", "推送公安"]
    priority: int = 50
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    """更新规则请求 (所有字段可选)."""
    rule_name: Optional[str] = None
    rule_category: Optional[TelecomRuleCategory] = None
    event_type: Optional[Literal["开户", "通话", "国际来电", "短信发送", "物联网激活", "通用"]] = None
    rule_condition: Optional[dict] = None
    risk_level: Optional[Literal["低", "中", "高", "极高"]] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action: Optional[Literal["通过", "标记", "人工审核", "拒绝", "关停号码", "推送公安"]] = None
    is_enabled: Optional[int] = None
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


class RuleListResponse(BaseModel):
    """规则列表响应 (分页)."""
    items: list[RuleResponse]
    total: int
    page: int
    page_size: int


# ============================================================
# 评估历史
# ============================================================

class AssessmentItem(BaseModel):
    """评估列表条目."""
    assessment_id: str
    event_id: str
    msisdn: str
    event_type: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    create_time: datetime


class AssessmentListResponse(BaseModel):
    """评估列表响应."""
    items: list[AssessmentItem]
    total: int
    page: int
    page_size: int


class AssessmentDetailResponse(BaseModel):
    """评估详情 (含命中规则 + ML 评分)."""
    assessment_id: str
    event_id: str
    msisdn: str
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
    """添加黑名单请求."""
    blacklist_type: Literal["号卡", "客户", "设备", "渠道"]
    blacklist_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None


class BlacklistResponse(BaseModel):
    """黑名单响应."""
    blacklist_id: int
    blacklist_type: str
    blacklist_value: str
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None
    create_time: Optional[datetime] = None


class BlacklistListResponse(BaseModel):
    """黑名单列表响应."""
    items: list[BlacklistResponse]
    total: int
    page: int
    page_size: int


# ============================================================
# 案件管理
# ============================================================

class CaseReviewRequest(BaseModel):
    """案件审核请求."""
    decision: Literal["已通过", "已拒绝", "已关闭", "已关停"]
    reviewer: str
    review_comment: Optional[str] = None
    add_to_blacklist: bool = False
    blacklist_expire_hours: Optional[int] = None


class CaseItem(BaseModel):
    """案件列表项."""
    case_id: str
    assessment_id: str
    msisdn: str
    case_status: str
    case_category: Optional[str] = None
    final_score: Optional[int] = None
    risk_level: Optional[str] = None
    create_time: Optional[datetime] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None


class CaseListResponse(BaseModel):
    """案件列表响应."""
    items: list[CaseItem]
    total: int
    page: int
    page_size: int


class CaseDetailResponse(BaseModel):
    """案件详情响应."""
    case_id: str
    assessment_id: str
    msisdn: str
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
    ml_score: Optional[float] = None
    ml_decision: Optional[str] = None
    source_id: Optional[str] = None
    event_type: Optional[str] = None


class CaseStatistics(BaseModel):
    """案件统计."""
    total: int = 0
    pending: int = 0       # 待审核
    reviewing: int = 0     # 审核中
    approved: int = 0      # 已通过
    rejected: int = 0      # 已拒绝
    closed: int = 0        # 已关闭
    halted: int = 0        # 已关停
    by_category: dict[str, int] = {}


# ============================================================
# 号卡风险画像
# ============================================================

class CardProfileResponse(BaseModel):
    """号卡风险画像响应."""
    msisdn: str
    risk_score: int = 0
    risk_level: str = "低"
    assessment_count: int = 0
    last_assessment_time: Optional[datetime] = None
    profile_data: Any = None


# ============================================================
# AI Agent
# ============================================================

class AgentChatRequest(BaseModel):
    """Agent 对话请求."""
    message: str
    session_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    """Agent 对话响应."""
    reply: str
    session_id: str


# ============================================================
# Demo: 演练 3 个典型 schema (无需 DB / 服务)
# 跑法: python app/schemas.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("电信风控 Pydantic Schema 演示")
    print("=" * 60)

    # 1. RiskCheckRequest — 入口
    req = RiskCheckRequest(
        event_type="通话", source_id="cdr_001", msisdn="13800000001",
        event_data={"called_no": "13900000000", "duration": 5},
    )
    print("\n[1] RiskCheckRequest (入口):")
    print(req.model_dump_json(indent=2))

    # 2. RiskCheckResponse — 7 步流水线返回
    hits = [
        RuleHitInfo(
            rule_id="R001", rule_name="GOIP短时高频主叫",
            rule_category="通话欺诈", risk_level="高",
            risk_score=70, action="人工审核",
            description="1小时内主叫超20次, GOIP虚拟拨号嫌疑",
        ),
    ]
    resp = RiskCheckResponse(
        assessment_id="ast_demo", event_id="evt_demo",
        msisdn="13800000001", final_score=70, risk_level="高", decision="人工审核",
        rule_count=1, triggered_rules=hits,
        features={"cdr_out_count_1h": 25, "dev_cards_on_imei": 1},
        create_time=datetime.now(),
        ml_score=0.82, ml_decision="人工审核",
    )
    print("\n[2] RiskCheckResponse (响应, 含 ML 评分):")
    print(f"  final_score = {resp.final_score}, risk_level = {resp.risk_level}, decision = {resp.decision}")
    print(f"  ml_score    = {resp.ml_score} (P 高风险)")
    print(f"  triggered_rules[0] = {resp.triggered_rules[0].rule_name}")

    # 3. AssessmentDetailResponse
    detail = AssessmentDetailResponse(
        assessment_id="ast_demo", event_id="evt_demo",
        msisdn="13800000001", event_type="通话", event_source_id="cdr_001",
        final_score=70, risk_level="高", decision="人工审核",
        rule_count=1, triggered_rules=hits,
        create_time=datetime.now(),
        ml_score=0.82, ml_decision="人工审核",
    )
    print(f"\n[3] AssessmentDetailResponse: 字段数={len(detail.model_dump())}")
    print("=" * 60)
    print("总结: schema 覆盖 风控检查/规则/黑名单/案件/画像/Agent/评估历史")
