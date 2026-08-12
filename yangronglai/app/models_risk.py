"""Risk-domain ORM models kept separate from bank business data."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class RiskRule(Base):
    """Versioned, data-driven rule definition."""

    __tablename__ = "risk_rule"

    rule_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scenarios: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index("idx_risk_rule_enabled_priority", "is_enabled", "priority"),
    )


class RiskEvent(Base):
    """Immutable audit snapshot of an incoming risk request."""

    __tablename__ = "risk_event"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_risk_event_source", "scenario", "source_id"),
        Index("idx_risk_event_user_time", "user_id", "created_at"),
    )


class RiskFeatureSnapshot(Base):
    """The exact feature vector used for one assessment."""

    __tablename__ = "risk_feature_snapshot"

    feature_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id"), nullable=False, unique=True)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False, default="bank-rule-v1")
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class RiskRuleHit(Base):
    """Matched rule details for audit and later effectiveness analysis."""

    __tablename__ = "risk_rule_hit"

    hit_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(ForeignKey("risk_rule.rule_id"), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    condition_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    hit_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("event_id", "rule_id", name="uq_rule_hit_event_rule"),
        Index("idx_rule_hit_rule_time", "rule_id", "hit_at"),
    )


class RiskAssessment(Base):
    """One complete rule/model/graph fusion outcome."""

    __tablename__ = "risk_assessment"

    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id"), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    graph_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_assessment_user_time", "user_id", "created_at"),
        Index("idx_assessment_decision_time", "decision", "created_at"),
        Index("idx_assessment_scenario_time", "scenario", "created_at"),
    )


class RiskLabel(Base):
    """Independent ground truth; never derived directly from a rule decision."""

    __tablename__ = "risk_label"

    label_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(24), nullable=False)
    label_source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    notes: Mapped[str | None] = mapped_column(Text)
    labeled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("scenario", "source_id", "label_source", name="uq_label_source"),
        Index("idx_label_user", "user_id"),
    )


class RiskCase(Base):
    """Manual-review queue item generated by high-risk assessments."""

    __tablename__ = "risk_case"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("risk_assessment.assessment_id"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    risk_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(64))
    review_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_case_status_time", "status", "created_at"),
        Index("idx_case_user", "user_id"),
    )


class RiskAppeal(Base):
    """Client appeal against an immutable rejected risk assessment."""

    __tablename__ = "risk_appeal"

    appeal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessment.assessment_id"), nullable=False, unique=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUBMITTED")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_resolution: Mapped[str | None] = mapped_column(String(200))
    appeal_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    review_due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    review_decision: Mapped[str | None] = mapped_column(String(32))
    reviewer: Mapped[str | None] = mapped_column(String(64))
    review_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_appeal_status_due", "status", "review_due_at"),
        Index("idx_appeal_user", "user_id"),
    )


class RiskAppealEvidence(Base):
    """Text or controlled-file metadata supplied for an appeal."""

    __tablename__ = "risk_appeal_evidence"

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("risk_appeal.appeal_id"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    statement: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    storage_reference: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RECEIVED")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_appeal_evidence_appeal", "appeal_id", "created_at"),
        UniqueConstraint("appeal_id", "file_sha256", name="uq_appeal_evidence_hash"),
    )


class RiskActionLog(Base):
    """Compliance audit trail for rule and case mutations."""

    __tablename__ = "risk_action_log"

    log_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(48), nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    remark: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_action_target", "target_type", "target_id"),
        Index("idx_action_operator_time", "operator", "created_at"),
    )


__all__ = [
    "RiskRule",
    "RiskEvent",
    "RiskFeatureSnapshot",
    "RiskRuleHit",
    "RiskAssessment",
    "RiskLabel",
    "RiskCase",
    "RiskAppeal",
    "RiskAppealEvidence",
    "RiskActionLog",
]
