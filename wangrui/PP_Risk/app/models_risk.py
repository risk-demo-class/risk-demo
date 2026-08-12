from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RiskRule(Base):
    __tablename__ = "risk_rule"
    rule_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, default="通用")
    rule_condition: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskEvent(Base):
    __tablename__ = "risk_event"
    event_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    event_source_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_data: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskFeature(Base):
    __tablename__ = "risk_feature"
    feature_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    compute_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"
    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rule_results: Mapped[str | None] = mapped_column(Text)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskCase(Base):
    __tablename__ = "risk_case"
    case_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    case_status: Mapped[str] = mapped_column(String(20), default="待审核")
    case_category: Mapped[str | None] = mapped_column(String(50))
    risk_detail: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(100))
    review_comment: Mapped[str | None] = mapped_column(Text)
    review_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[str | None] = mapped_column(String(50))
    event_type: Mapped[str | None] = mapped_column(String(40))
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskBlacklist(Base):
    __tablename__ = "risk_blacklist"
    __table_args__ = (UniqueConstraint("blacklist_type", "blacklist_value"),)
    blacklist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    blacklist_type: Mapped[str] = mapped_column(String(30), nullable=False)
    blacklist_value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    expire_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskUserProfile(Base):
    __tablename__ = "risk_user_profile"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default="低")
    assessment_count: Mapped[int] = mapped_column(Integer, default=0)
    profile_data: Mapped[str | None] = mapped_column(Text)
    last_assessment_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskActionLog(Base):
    __tablename__ = "risk_action_log"
    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskAlert(Base):
    __tablename__ = "risk_alert"
    alert_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    alert_level: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_status: Mapped[str] = mapped_column(String(20), default="待处理")
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(50), nullable=False)
    alert_detail: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


RISK_MODELS = (RiskRule, RiskEvent, RiskFeature, RiskAssessment, RiskCase, RiskBlacklist, RiskUserProfile, RiskActionLog, RiskAlert)

