"""Model 层：教育风控的规则、审计、评估、案件与黑名单实体。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RiskRule(Base):
    __tablename__ = "risk_rule"
    rule_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    rule_condition: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True)


class RiskBlacklist(Base):
    __tablename__ = "risk_blacklist"
    blacklist_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blacklist_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    blacklist_value: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)


class RiskEvent(Base):
    __tablename__ = "risk_event"
    event_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class RiskFeature(Base):
    __tablename__ = "risk_feature"
    feature_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[float] = mapped_column(Float, nullable=False)


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"
    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("risk_event.event_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_results: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class RiskCase(Base):
    __tablename__ = "risk_case"
    case_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("risk_assessment.assessment_id"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    case_status: Mapped[str] = mapped_column(String(20), nullable=False, default="待审核")
