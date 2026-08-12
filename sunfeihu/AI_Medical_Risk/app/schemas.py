"""Pydantic 请求/响应契约: API 端点的数据校验和序列化 (P0 仅定义风控检查请求)

事件类型已改为医疗语义 (PRD §6):
- 挂号申请 / 挂号退号 → source_id = registration_id
- 处方开立           → source_id = prescription_id
- 医保结算           → source_id = claim_id
user_id 对应患者 ID (PRD §7.3).
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# 医疗事件类型 (与 service/validator.EVENT_SOURCE_MAP 保持单一来源)
MedicalEventType = Literal["挂号申请", "挂号退号", "处方开立", "医保结算"]


class RiskCheckRequest(BaseModel):
    """风险检查请求 (P0 校验契约)"""
    event_type: MedicalEventType
    source_id: str = Field(description="关联业务ID (registration_id / prescription_id / claim_id)")
    user_id: str = Field(description="患者ID (与 source_id 记录归属一致)")
    event_data: Optional[dict] = None


class RuleHitInfo(BaseModel):
    """规则命中信息 (占位, P1 填充)"""
    rule_id: str
    rule_name: str
    rule_category: str
    risk_level: str
    risk_score: int
    action: str
    description: Optional[str] = None


class RiskCheckResponse(BaseModel):
    """风险检查响应 (占位, P1 填充)"""
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


class CaseReviewRequest(BaseModel):
    case_status: Literal["审核中", "已通过", "已拒绝", "已关闭"]
    reviewer: str = Field(min_length=1, max_length=50)
    review_comment: str = Field(default="", max_length=1000)


class BlacklistCreateRequest(BaseModel):
    blacklist_type: Literal[
        "PATIENT_ID", "ID_CARD_HASH", "INSURANCE_CARD_HASH", "PHONE_HASH",
        "DOCTOR_ID", "DEVICE_ID_HASH", "HOSPITAL_ID",
    ]
    blacklist_value: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=500)
    expire_time: datetime | None = None


class AgentChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AgentChatResponse(BaseModel):
    answer: str
    intent: str
    llm_used: bool
    safety_disclaimer: str = "仅供医疗风控辅助，不构成诊断、治疗或用药建议。"


class AlertResolveRequest(BaseModel):
    status: Literal["HANDLING", "RESOLVED", "IGNORED"] = "RESOLVED"
    handler: str = Field(min_length=1, max_length=50)


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=50)


class UserCreateRequest(UserRegisterRequest):
    role: Literal["admin", "reviewer", "analyst", "viewer"] = "viewer"


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    role: Literal["admin", "reviewer", "analyst", "viewer"] | None = None
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class RuleCreateRequest(BaseModel):
    rule_id: str = Field(min_length=3, max_length=50, pattern=r"^[A-Z][A-Z0-9_-]+$")
    rule_name: str = Field(min_length=2, max_length=100)
    rule_category: Literal["医保结算异常", "处方合规", "挂号行为", "通用"]
    event_type: Literal["挂号申请", "挂号退号", "处方开立", "医保结算", "通用"]
    condition: dict[str, Any]
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    description: str = Field(default="", max_length=500)
    priority: int = Field(default=0, ge=0, le=999)


class RuleUpdateRequest(BaseModel):
    rule_name: str = Field(min_length=2, max_length=100)
    rule_category: Literal["医保结算异常", "处方合规", "挂号行为", "通用"]
    event_type: Literal["挂号申请", "挂号退号", "处方开立", "医保结算", "通用"]
    condition: dict[str, Any]
    risk_level: Literal["低", "中", "高", "极高"]
    risk_score: int = Field(ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"]
    description: str = Field(default="", max_length=500)
    priority: int = Field(default=0, ge=0, le=999)


class CaseAssignRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=50)
    comment: str = Field(default="", max_length=1000)


class CaseReopenRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=2, max_length=1000)


# ============================================================
# Demo: 演练 RiskCheckRequest 构造 (医疗事件)
# 跑法: uv run python app/schemas.py
# ============================================================
if __name__ == "__main__":
    import json

    print("=" * 60)
    print("Pydantic Schema 演示 (医疗事件请求)")
    print("=" * 60)

    req = RiskCheckRequest(
        event_type="医保结算", source_id="CLM000001", user_id="PAT000001",
        event_data={"total_amount": 15000, "claim_type": "异地就医"},
    )
    print("\n[1] RiskCheckRequest (医保结算):")
    print(req.model_dump_json(indent=2))

    print("\n说明: event_type 限定为 4 类医疗事件, source_id 必须是对应业务表主键,")
    print("user_id 必须是患者ID, 且 source_id 记录须归属该患者 (service/validator 校验).")
