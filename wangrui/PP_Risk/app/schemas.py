from typing import Any, Literal

from pydantic import BaseModel, Field


TechnicalEventType = Literal["下单", "支付", "售后申请", "物流投诉"]


class RiskCheckRequest(BaseModel):
    event_type: TechnicalEventType
    source_id: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=50)
    order_id: str | None = None
    receive_id: str | None = None
    event_data: dict[str, Any] = Field(default_factory=dict)


class RuleHitInfo(BaseModel):
    rule_id: str
    rule_name: str
    risk_score: int
    action: str


class RiskCheckResponse(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[RuleHitInfo]

