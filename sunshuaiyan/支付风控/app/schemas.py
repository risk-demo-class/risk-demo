from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class InboundRiskRequest(BaseModel):
    inbound_payment_id: int = Field(gt=0)
    persist: bool = True


class PayoutRiskRequest(BaseModel):
    payout_id: int = Field(gt=0)
    persist: bool = True


class RiskWorkbenchRequest(BaseModel):
    event_type: Literal["INBOUND", "PAYOUT"]
    business_id: str = Field(min_length=1, max_length=64)
    persist: bool = True

    @field_validator("business_id")
    @classmethod
    def clean_business_id(cls, value: str) -> str:
        return value.strip()


BlacklistEntityType = Literal[
    "CUSTOMER",
    "COUNTERPARTY",
    "BANK_ACCOUNT",
    "VIRTUAL_ACCOUNT",
    "DEVICE",
    "DOCUMENT_HASH",
    "COUNTRY",
]


class BlacklistCreate(BaseModel):
    entity_type: BlacklistEntityType
    entity_value: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    reason_code: str = Field(min_length=2, max_length=48)
    reason_detail: str | None = Field(default=None, max_length=512)
    severity: Literal["MEDIUM", "HIGH", "CRITICAL"] = "HIGH"
    source: Literal["MANUAL", "CASE", "SCREENING", "EXTERNAL"] = "MANUAL"
    source_refs: list[str] | None = None
    expires_at: datetime | None = None
    created_by: str = Field(default="risk-operator", max_length=64)

    @field_validator("entity_value", "reason_code", "created_by")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        return value.strip()


class BlacklistRemoveRequest(BaseModel):
    removed_by: str = Field(default="risk-operator", max_length=64)
    removed_reason: str = Field(default="manual removal", min_length=2, max_length=255)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=80)


class AgentClearRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
