"""Shared API schemas for the bank risk platform."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Scenario(StrEnum):
    CARD = "CARD"
    LOAN = "LOAN"
    TRANSFER = "TRANSFER"
    LOGIN = "LOGIN"


class RiskLevel(StrEnum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    CRITICAL = "极高"


class Decision(StrEnum):
    PASS = "通过"
    FLAG = "标记"
    REVIEW = "人工审核"
    REJECT = "拒绝"


class AppealStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    NEEDS_INFO = "NEEDS_INFO"
    DECISION_UPHELD = "DECISION_UPHELD"
    DECISION_OVERTURNED = "DECISION_OVERTURNED"
    CLOSED = "CLOSED"


class AppealReviewDecision(StrEnum):
    UPHOLD = "UPHOLD"
    OVERTURN = "OVERTURN"
    MORE_INFO_REQUIRED = "MORE_INFO_REQUIRED"


class AppealEvidenceType(StrEnum):
    STATEMENT = "STATEMENT"
    TRANSACTION_PROOF = "TRANSACTION_PROOF"
    IDENTITY_PROOF = "IDENTITY_PROOF"
    OTHER = "OTHER"


class ComponentScore(BaseModel):
    component: str
    enabled: bool
    score: int | None = Field(default=None, ge=0, le=100)
    version: str | None = None


class RiskCheckRequest(BaseModel):
    """Unified event contract; persisted business records can hydrate event_data."""

    scenario: Scenario
    source_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    event_data: dict[str, Any] = Field(default_factory=dict)


class RuleHitResponse(BaseModel):
    rule_id: str
    rule_name: str
    risk_score: int
    risk_level: RiskLevel
    decision: Decision
    evidence: dict[str, Any]
    version: str


class ScoreBreakdown(BaseModel):
    formula: str
    highest_rule_score: int = Field(ge=0, le=100)
    other_rules_score_sum: int = Field(ge=0)
    additional_weight: float = Field(ge=0, le=1)
    weighted_addition: float = Field(ge=0)
    raw_score: float = Field(ge=0)
    capped_at_100: bool


class FusionBreakdown(BaseModel):
    formula: str
    component_scores: dict[str, int]
    primary_component: str
    primary_score: int
    other_components_score_sum: int
    additional_weight: float
    weighted_addition: float
    raw_score: float
    capped_at_100: bool


class AppealOption(BaseModel):
    allowed: bool
    deadline: datetime | None = None
    page_url: str | None = None
    submit_url: str | None = None
    token: str | None = None


class RiskCheckResponse(BaseModel):
    request_id: str
    event_id: str
    assessment_id: str
    scenario: Scenario
    stage: str
    final_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    decision: Decision
    hit_count: int = Field(ge=0)
    hits: list[RuleHitResponse]
    score_breakdown: ScoreBreakdown
    fusion_breakdown: FusionBreakdown
    components: list[ComponentScore]
    appeal: AppealOption
    message: str


class AppealSubmissionRequest(BaseModel):
    assessment_id: str = Field(min_length=1, max_length=64)
    appeal_token: str = Field(min_length=32, max_length=2048)
    reason: str = Field(min_length=10, max_length=2000)
    requested_resolution: str | None = Field(default=None, max_length=200)


class AppealEvidenceRequest(BaseModel):
    evidence_type: AppealEvidenceType
    statement: str | None = Field(default=None, max_length=4000)
    file_name: str | None = Field(default=None, max_length=255)
    file_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @model_validator(mode="after")
    def require_statement_or_file(self) -> "AppealEvidenceRequest":
        if not self.statement and not self.file_sha256:
            raise ValueError("statement 或 file_sha256 至少提供一项")
        if self.file_name and not self.file_sha256:
            raise ValueError("提供 file_name 时必须同时提供 file_sha256")
        return self


class AppealReviewRequest(BaseModel):
    decision: AppealReviewDecision
    reviewer: str = Field(min_length=1, max_length=64)
    comment: str = Field(min_length=2, max_length=2000)


class AppealEvidenceResponse(BaseModel):
    evidence_id: str
    evidence_type: AppealEvidenceType
    statement: str | None
    file_name: str | None
    file_sha256: str | None
    status: str
    created_at: datetime


class AppealResponse(BaseModel):
    appeal_id: str
    assessment_id: str
    scenario: Scenario
    status: AppealStatus
    reason: str
    requested_resolution: str | None
    appeal_deadline: datetime
    review_due_at: datetime
    review_decision: str | None
    review_comment: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    original_assessment: dict[str, Any]
    evidence: list[AppealEvidenceResponse]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    stage: str
    timestamp: datetime
    components: dict[str, bool]


class RuleSummaryResponse(BaseModel):
    rule_id: str
    rule_name: str
    scenarios: list[Scenario]
    condition: dict[str, Any]
    risk_level: RiskLevel
    risk_score: int
    decision: Decision
    priority: int
    version: str
    is_enabled: bool
    description: str

    model_config = {"from_attributes": True}


class AssessmentResponse(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    scenario: Scenario
    rule_score: int
    final_score: int
    risk_level: RiskLevel
    decision: Decision
    hit_count: int
    rule_results: list[dict[str, Any]]
    decision_reason: str
    created_at: datetime

    model_config = {"from_attributes": True}
