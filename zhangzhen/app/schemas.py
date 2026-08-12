"""HTTP 请求与响应契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Decision, EventType, RiskLevel


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    environment: str
    business_table_count: int
    risk_table_count: int
    registered_table_count: int


class ReadinessResponse(ApiModel):
    status: Literal["ready"]
    database: Literal["available"]


class RiskCheckRequest(ApiModel):
    """一次风险检查的稳定四字段契约。"""

    event_type: EventType
    source_id: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=50)
    event_data: dict[str, object] = Field(default_factory=dict)

    @field_validator("source_id", "user_id")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标识不能为空")
        return value


class TriggeredRule(ApiModel):
    rule_id: str
    rule_name: str
    risk_level: RiskLevel
    risk_score: int
    action: Decision
    condition: dict[str, object]
    actual_values: dict[str, float]


class RiskCheckResponse(ApiModel):
    """正常决策和黑名单短路共用的响应。"""

    assessment_id: str | None = None
    event_id: str | None = None
    user_id: str
    final_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    decision: Decision
    rule_count: int = Field(default=0, ge=0)
    triggered_rules: list[TriggeredRule] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    ml_score: float | None = Field(default=None, ge=0, le=1)
    ml_decision: Decision | None = None
    message: str | None = None
    blocked_by: str | None = None
    create_time: datetime
