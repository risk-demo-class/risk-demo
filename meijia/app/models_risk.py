"""最小可用风控平台表 ORM。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RiskRule(Base):
    __tablename__ = "risk_rule"
    rule_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(30), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_condition: Mapped[dict] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column("is_enabled", Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        Index("idx_rule_event_enabled", "event_type", "is_enabled", "deleted_at", "priority"),
        CheckConstraint("risk_level IN ('低','中','高','极高')", name="chk_rule_level"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="chk_rule_score"),
        CheckConstraint("action IN ('通过','标记','人工审核','拒绝')", name="chk_rule_action"),
    )


class RiskEvent(Base):
    __tablename__ = "risk_event"
    event_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_source_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    event_data: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("idx_event_user_time", "user_id", "occurred_at"),
        Index("idx_event_source", "event_type", "event_source_id"),
    )


class RiskFeature(Base):
    __tablename__ = "risk_feature"
    feature_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[object] = mapped_column(JSON, nullable=False)
    data_as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("event_id", "entity_type", "entity_id", "feature_name", name="uk_feature_event_name"),
        Index("idx_feature_entity", "entity_type", "entity_id", "feature_name", "computed_at"),
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"
    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id", ondelete="RESTRICT", onupdate="CASCADE"), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    rule_results: Mapped[list] = mapped_column(JSON, nullable=False)
    rule_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    final_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    blocked_by: Mapped[str | None] = mapped_column(String(30))
    ml_score: Mapped[float | None] = mapped_column(Float)
    ml_decision: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("idx_assessment_user_time", "user_id", "created_at"),
        Index("idx_assessment_decision_time", "decision", "created_at"),
        CheckConstraint("final_score BETWEEN 0 AND 100", name="chk_assessment_score"),
        CheckConstraint("risk_level IN ('低','中','高','极高')", name="chk_assessment_level"),
        CheckConstraint("decision IN ('通过','标记','人工审核','拒绝')", name="chk_assessment_decision"),
    )


class RiskCase(Base):
    __tablename__ = "risk_case"
    case_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("risk_assessment.assessment_id", ondelete="RESTRICT", onupdate="CASCADE"), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    case_status: Mapped[str] = mapped_column(String(20), default="待审核", nullable=False)
    case_category: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_detail: Mapped[dict | None] = mapped_column(JSON)
    reviewer: Mapped[str | None] = mapped_column(String(50))
    review_comment: Mapped[str | None] = mapped_column(String(1000))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (
        Index("idx_case_status_time", "case_status", "created_at"),
        Index("idx_case_user_time", "user_id", "created_at"),
        CheckConstraint("case_status IN ('待审核','审核中','已通过','已拒绝','已关闭')", name="chk_case_status"),
    )


class RiskAlert(Base):
    """风控告警 (P4-L2): 系统自己发现异常 (案件积压/命中率突降/拒绝率过高等)。"""
    __tablename__ = "risk_alert"
    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)      # BUSINESS / MODEL
    alert_level: Mapped[str] = mapped_column(String(10), nullable=False)     # P1 / P2
    alert_title: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_content: Mapped[str] = mapped_column(String(1000), nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(100))
    metric_value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    handler: Mapped[str | None] = mapped_column(String(50))
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    resolve_time: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        Index("idx_alert_status_time", "status", "create_time"),
        CheckConstraint("alert_type IN ('BUSINESS','MODEL')", name="chk_alert_type"),
        CheckConstraint("alert_level IN ('P1','P2')", name="chk_alert_level"),
        CheckConstraint("status IN ('PENDING','HANDLING','RESOLVED','IGNORED')", name="chk_alert_status"),
    )


class RiskActionLog(Base):
    """操作审计日志 (P4-L1): 规则/案件/黑名单的每次变更都留痕, 合规要求。"""
    __tablename__ = "risk_action_log"
    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)     # rule / case / blacklist
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    before_value: Mapped[dict | None] = mapped_column(JSON)
    after_value: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(50))
    remark: Mapped[str | None] = mapped_column(String(500))
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("idx_actionlog_target", "target_type", "target_id"),
        Index("idx_actionlog_time", "create_time"),
    )
