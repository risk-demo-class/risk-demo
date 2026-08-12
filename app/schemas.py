from typing import Literal

from pydantic import BaseModel, Field


class RiskCheckRequest(BaseModel):
    event_type: Literal["课程报名", "退费申请", "学历认证"]
    source_id: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=50)


class RuleHitInfo(BaseModel):
    rule_id: str
    rule_name: str
    risk_score: int


class RiskCheckResponse(BaseModel):
    event_id: str
    assessment_id: str
    user_id: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]
    blocked_by: str | None = None


class RuleListItem(BaseModel):
    rule_id: str
    rule_name: str
    event_type: str
    risk_score: int
    action: str
    is_enabled: bool


class RuleListResponse(BaseModel):
    items: list[RuleListItem]
    total: int
    page: int
    page_size: int


class CaseListItem(BaseModel):
    case_id: str
    assessment_id: str
    source_id: str
    user_id: str
    event_type: str
    case_status: str


class CaseListResponse(BaseModel):
    items: list[CaseListItem]
    total: int
    page: int
    page_size: int


class CaseReviewRequest(BaseModel):
    decision: Literal["审核中", "已通过", "已拒绝", "已关闭"]


class AssessmentListItem(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    final_score: int
    risk_level: str
    decision: str
    event_type: str
    source_id: str


class AssessmentListResponse(BaseModel):
    items: list[AssessmentListItem]
    total: int
    page: int
    page_size: int


class BlacklistCreate(BaseModel):
    blacklist_type: Literal["用户", "证件哈希", "设备哈希"]
    blacklist_value: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=500)


class BlacklistItem(BaseModel):
    blacklist_id: int
    blacklist_type: str
    blacklist_value: str
    reason: str | None


class BlacklistListResponse(BaseModel):
    items: list[BlacklistItem]
    total: int
    page: int
    page_size: int
