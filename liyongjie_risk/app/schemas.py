"""
银行风控系统 - Pydantic 数据模型 (请求/响应)
============================================
定义 API 接口的输入输出 Schema, 含风控检查请求/响应、规则配置、案件管理等.
"""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ============================================================
# 风控检查
# ============================================================

class RiskCheckRequest(BaseModel):
    """
    风控检查请求 — 统一事件格式 (PRD 第 5 节)
    -----------------------------------------
    字段对应 PRD 定义的统一事件字段:
      event_id, event_type, user_id, card_id, device_id,
      ip, geo, amount, channel, event_at
    """
    event_type: str = Field(
        ...,
        description="事件类型: LOGIN/TRANSFER/LOAN_APPLY/CARD_APPLY/PAYMENT/WITHDRAW/REPAY/...",
    )
    user_id: int = Field(..., description="用户 ID")
    card_id: Optional[int] = Field(None, description="关联卡 ID (转账/支付场景)")
    device_id: Optional[int] = Field(None, description="设备 ID")
    ip: Optional[str] = Field(None, description="客户端 IP")
    geo: Optional[str] = Field(None, description="省市, 如 北京-北京市")
    amount: Optional[float] = Field(None, description="金额 (转账/贷款场景)")
    channel: Optional[str] = Field("APP", description="渠道: APP/网银/ATM/POS/第三方")

    # 扩展字段 — 按事件类型可选
    to_card_id: Optional[int] = Field(None, description="收款卡 ID (转账场景)")
    to_card_no_hash: Optional[str] = Field(None, description="收款卡号哈希 (跨行转账)")
    to_account_name_hash: Optional[str] = Field(None, description="收款方户名哈希")
    to_bank_code: Optional[str] = Field(None, description="收款方银行代码")

    # 贷款专用字段
    term_months: Optional[int] = Field(None, description="贷款期限（月）")
    purpose: Optional[str] = Field(None, description="贷款用途")
    monthly_income: Optional[float] = Field(None, description="月收入")
    debt_ratio: Optional[float] = Field(None, description="负债率")
    credit_query_1m: Optional[int] = Field(0, description="近 1 月征信查询次数")

    # 扩展数据
    event_data: Optional[dict] = Field(default_factory=dict, description="扩展事件数据 (JSON)")

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "TRANSFER",
                "user_id": 1,
                "card_id": 1,
                "device_id": 5,
                "ip": "202.96.128.86",
                "geo": "广东-广州市",
                "amount": 80000.00,
                "channel": "APP",
                "to_card_no_hash": "abc123...",
                "to_bank_code": "ICBC",
            }
        }


class RuleHitInfo(BaseModel):
    """命中规则详情 (嵌入 RiskCheckResponse)"""
    rule_id: str
    rule_name: str
    scene: str = ""
    risk_level: int = 1
    risk_score: float = 0
    decision: str = "PASS"
    action: Optional[str] = None
    description: str = ""


class RiskCheckResponse(BaseModel):
    """风控检查响应"""
    assessment_id: str = ""
    event_id: str = ""
    user_id: int
    final_score: int = 0
    risk_level: str = "低"
    decision: str = "通过"
    rule_count: int = 0
    triggered_rules: list[RuleHitInfo] = Field(default_factory=list)
    features: dict = Field(default_factory=dict)
    create_time: datetime = Field(default_factory=datetime.now)
    ml_score: float = 0.0
    ml_decision: str = "通过"
    blocked_by: Optional[str] = None
    action: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "assessment_id": "ast_01abc...",
                "event_id": "evt_01def...",
                "user_id": 1,
                "final_score": 95,
                "risk_level": "极高",
                "decision": "拒绝",
                "rule_count": 2,
                "triggered_rules": [
                    {"rule_id": "R001", "rule_name": "异地大额转账", "risk_level": 4, "risk_score": 95}
                ],
            }
        }


# ============================================================
# 规则配置
# ============================================================

class RuleConfigRequest(BaseModel):
    """规则配置请求"""
    rule_id: str = Field(..., description="规则编号 (R001-R099)")
    rule_name: str = Field(..., description="规则名称")
    scene: str = Field(..., description="所属场景: 登录/转账/贷款/信用卡")
    conditions: dict = Field(..., description="条件表达式 JSON")
    risk_level: int = Field(..., description="风险等级: 1=低, 2=中, 3=高, 4=极高")
    decision: str = Field(..., description="决策: PASS/CHALLENGE/MANUAL/REJECT")
    action: Optional[str] = Field(None, description="处置动作")
    priority: int = Field(100, description="优先级, 小者先执行")
    status: int = Field(1, description="状态: 1=启用, 0=停用")


class RuleConfigResponse(BaseModel):
    """规则配置响应"""
    rule_id: str
    rule_name: str
    scene: str
    category: str = ""       # 前端兼容字段 (等同于 scene)
    name: str = ""           # 前端兼容字段
    conditions: dict
    risk_level: int
    score: int = 20          # 风险分值 (前端使用)
    rule_score: int = 20     # 前端兼容字段
    decision: str
    action: Optional[str] = None
    priority: int
    status: int
    is_enabled: bool = True  # 前端兼容字段
    enabled: bool = True     # 前端兼容字段
    description: str = ""    # 规则描述
    desc: str = ""           # 前端兼容字段
    updated_at: Optional[datetime] = None


# ============================================================
# 黑名单
# ============================================================

class BlacklistRequest(BaseModel):
    """黑名单创建请求"""
    type: int = Field(..., description="名单类型: 1=设备, 2=IP, 3=银行卡号, 4=身份证, 5=手机号")
    value: str = Field(..., description="命中值 (哈希或原文)")
    reason: Optional[str] = Field(None, description="入单原因")
    source: str = Field("内部", description="来源")
    risk_level: int = Field(3, description="风险等级: 1-4")
    expire_at: Optional[datetime] = Field(None, description="过期时间")


# ============================================================
# 画像
# ============================================================

class UserProfileResponse(BaseModel):
    """用户画像响应"""
    user_id: int
    common_city: Optional[str] = None
    common_device_id: Optional[int] = None
    avg_txn_amount: Optional[float] = None
    txn_freq_day: Optional[float] = None
    active_hours: Optional[str] = None
    risk_score: Optional[float] = None
    profile_at: Optional[datetime] = None


# ============================================================
# Dashboard
# ============================================================

class DashboardStatsResponse(BaseModel):
    """仪表盘统计"""
    total_users: int = 0
    total_transactions: int = 0
    total_risk_events: int = 0
    high_risk_count: int = 0
    blocked_count: int = 0
    manual_review_count: int = 0
    rule_hit_distribution: list[dict] = Field(default_factory=list)
    risk_event_trend: list[dict] = Field(default_factory=list)
    recent_events: list[dict] = Field(default_factory=list)


# ============================================================
# AI Agent 对话
# ============================================================

class AgentChatRequest(BaseModel):
    """AI Agent 对话请求"""
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID")
    context: Optional[dict] = Field(default_factory=dict, description="上下文 (如当前查看的案件)")


class AgentChatResponse(BaseModel):
    """AI Agent 对话响应"""
    reply: str
    session_id: Optional[str] = None
    tool_calls_made: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================
# 规则列表 (分页)
# ============================================================

class RuleListResponse(BaseModel):
    """规则列表分页响应"""
    items: list[RuleConfigResponse]
    total: int
    page: int = 1
    page_size: int = 20


class RuleCreateUpdateRequest(BaseModel):
    """规则创建/更新请求"""
    rule_id: str = Field(..., description="规则编号 (R001-R099)")
    rule_name: str = Field(..., description="规则名称")
    category: Optional[str] = Field(None, description="场景分类 (LOGIN/TRANSFER/LOAN/CARD)")
    risk_level: int = Field(1, description="风险等级: 1=低, 2=中, 3=高, 4=极高")
    score: int = Field(20, description="风险分值 (0-100)")
    action: str = Field("PASS", description="处置动作: PASS/CHALLENGE/MANUAL/REJECT")
    priority: int = Field(5, description="优先级")
    condition: Optional[str] = Field(None, description="条件表达式 (JSON 字符串)")
    description: Optional[str] = Field(None, description="规则描述")


class ToggleRuleRequest(BaseModel):
    """规则启停请求"""
    enabled: bool = Field(..., description="是否启用")


# ============================================================
# 风险事件列表
# ============================================================

class RiskEventItem(BaseModel):
    """风险事件列表项"""
    event_id: int
    event_type: str
    user_id: Optional[int] = None
    card_id: Optional[int] = None
    device_id: Optional[int] = None
    ip: Optional[str] = None
    amount: Optional[float] = None
    rule_ids: Optional[str] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    decision: Optional[str] = None
    action: Optional[str] = None
    status: Optional[int] = None
    handler: Optional[str] = None
    handled_at: Optional[datetime] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RiskEventListResponse(BaseModel):
    """风险事件列表分页响应"""
    items: list[RiskEventItem]
    total: int
    page: int = 1
    page_size: int = 20


# ============================================================
# 黑名单
# ============================================================

class BlacklistCreateRequest(BaseModel):
    """黑名单创建请求"""
    type_name: Optional[str] = Field(None, description="黑名单类型名称: 身份证/银行卡号/设备ID/IP地址")
    type: Optional[str] = Field(None, description="黑名单类型: IDCARD/BANKCARD/DEVICE/IP")
    value: str = Field(..., description="黑名单值")
    reason: Optional[str] = Field(None, description="拉黑原因")
    expire_time: Optional[str] = Field(None, description="过期时间 (ISO 格式)")


class BlacklistEntryResponse(BaseModel):
    """黑名单条目响应"""
    id: int
    type: Optional[str] = None
    bl_type: Optional[str] = None
    value: Optional[str] = None
    blacklist_value: Optional[str] = None
    reason: Optional[str] = None
    expire_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    create_time: Optional[datetime] = None
    status: Optional[int] = None
    risk_level: Optional[int] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class BlacklistListResponse(BaseModel):
    """黑名单列表分页响应"""
    items: list[BlacklistEntryResponse]
    total: int
    page: int = 1
    page_size: int = 20
