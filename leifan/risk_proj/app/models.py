from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def created_at_column() -> Mapped[datetime]:
    return mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        onupdate=func.current_timestamp(),
    )


class UserInfo(Base):
    __tablename__ = "user_info"
    __table_args__ = (
        Index("ix_user_info_name", "name"),
        Index("ix_user_info_real_name_status", "real_name_status"),
        Index("ix_user_info_vip_level", "vip_level"),
        Index("ix_user_info_registered_at", "registered_at"),
        Index("ix_user_info_account_age_days", "account_age_days"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    real_name_status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    vip_level: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'NORMAL'")
    )
    registered_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    account_age_days: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class PaymentAccount(Base):
    __tablename__ = "payment_account"
    __table_args__ = (
        UniqueConstraint("account_token_hash", name="uq_payment_account_token_hash"),
        Index("ix_payment_account_user_id", "user_id"),
        Index("ix_payment_account_type", "account_type"),
        Index("ix_payment_account_status", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    payment_account_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    account_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'ACTIVE'")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class OrderInfo(Base):
    __tablename__ = "order_info"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_order_info_order_no"),
        CheckConstraint("total_amount >= 0", name="ck_order_info_total_amount"),
        CheckConstraint("passenger_count >= 1", name="ck_order_info_passenger_count"),
        Index("ix_order_info_user_time", "user_id", "order_time"),
        Index("ix_order_info_payment_time", "payment_account_id", "order_time"),
        Index("ix_order_info_type_time", "order_type", "order_time"),
        Index("ix_order_info_cross_border_amount", "is_cross_border", "total_amount"),
        Index("ix_order_info_dest_country", "dest_country"),
        Index("ix_order_info_depart_date", "depart_date"),
        Index("ix_order_info_order_status", "order_status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    order_no: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    payment_account_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey(
            "payment_account.payment_account_id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'CNY'")
    )
    dest_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_cross_border: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    order_time: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    depart_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    passenger_count: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    order_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'CREATED'")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class PassengerInfo(Base):
    __tablename__ = "passenger_info"
    __table_args__ = (
        UniqueConstraint("id_type", "id_number_hash", name="uq_passenger_identity"),
        Index("ix_passenger_info_name", "name"),
        Index("ix_passenger_info_nationality", "nationality"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    passenger_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    id_type: Mapped[str] = mapped_column(String(20), nullable=False)
    id_number_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    id_number_masked: Mapped[str] = mapped_column(String(64), nullable=False)
    nationality: Mapped[str] = mapped_column(String(2), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class OrderPassenger(Base):
    __tablename__ = "order_passenger"
    __table_args__ = (
        Index("ix_order_passenger_passenger_id", "passenger_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        primary_key=True,
    )
    passenger_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey(
            "passenger_info.passenger_id", ondelete="RESTRICT", onupdate="CASCADE"
        ),
        primary_key=True,
    )
    passenger_role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_column()


class VisaApplication(Base):
    __tablename__ = "visa_application"
    __table_args__ = (
        UniqueConstraint("order_id", "passenger_id", name="uq_visa_order_passenger"),
        CheckConstraint("reject_history >= 0", name="ck_visa_reject_history"),
        Index(
            "ix_visa_user_status_decided",
            "user_id",
            "application_status",
            "decided_at",
        ),
        Index(
            "ix_visa_user_country_submit",
            "user_id",
            "dest_country",
            "submit_time",
        ),
        Index("ix_visa_passenger_id", "passenger_id"),
        Index("ix_visa_type", "visa_type"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    visa_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    passenger_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey(
            "passenger_info.passenger_id", ondelete="RESTRICT", onupdate="CASCADE"
        ),
        nullable=False,
    )
    dest_country: Mapped[str] = mapped_column(String(2), nullable=False)
    visa_type: Mapped[str] = mapped_column(String(40), nullable=False)
    application_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reject_history: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False, server_default=text("0")
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submit_time: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class BookingHotel(Base):
    __tablename__ = "booking_hotel"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_booking_hotel_order_id"),
        CheckConstraint("room_count >= 1", name="ck_booking_hotel_room_count"),
        Index("ix_booking_hotel_hotel_checkin", "hotel_id", "check_in"),
        Index("ix_booking_hotel_refundable", "is_refundable"),
        Index("ix_booking_hotel_city_code", "city_code"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    booking_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    hotel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    room_count: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    is_refundable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    city_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class BookingFlight(Base):
    __tablename__ = "booking_flight"
    __table_args__ = (
        UniqueConstraint("order_id", "segment_no", name="uq_flight_order_segment"),
        CheckConstraint("ticket_count >= 1", name="ck_booking_flight_ticket_count"),
        CheckConstraint("segment_no >= 1", name="ck_booking_flight_segment_no"),
        Index("ix_flight_no_date", "flight_no", "flight_date"),
        Index("ix_flight_depart_airport", "depart_airport"),
        Index("ix_flight_arrive_airport", "arrive_airport"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    booking_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    depart_airport: Mapped[str] = mapped_column(String(3), nullable=False)
    arrive_airport: Mapped[str] = mapped_column(String(3), nullable=False)
    cabin_class: Mapped[str] = mapped_column(String(20), nullable=False)
    ticket_count: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    segment_no: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class BookingTour(Base):
    __tablename__ = "booking_tour"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_booking_tour_order_id"),
        CheckConstraint("traveler_count >= 1", name="ck_booking_tour_traveler_count"),
        Index("ix_booking_tour_code", "tour_code"),
        Index("ix_booking_tour_route_type", "route_type"),
        Index("ix_booking_tour_group_code", "group_code"),
        Index("ix_booking_tour_departure_date", "departure_date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    booking_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    tour_code: Mapped[str] = mapped_column(String(40), nullable=False)
    tour_name: Mapped[str] = mapped_column(String(200), nullable=False)
    route_type: Mapped[str] = mapped_column(String(20), nullable=False)
    group_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    traveler_count: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class BlacklistExtra(Base):
    __tablename__ = "blacklist_extra"
    __table_args__ = (
        UniqueConstraint("entry_type", "value_hash", name="uq_blacklist_type_value"),
        Index("ix_blacklist_status_expire", "status", "expire_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    entry_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    value_masked: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'ACTIVE'")
    )
    effective_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    expire_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'system_reviewer'")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class RiskRule(Base):
    __tablename__ = "risk_rule"
    __table_args__ = (
        UniqueConstraint("rule_code", name="uq_risk_rule_code"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_rule_score"),
        CheckConstraint("rule_version >= 1", name="ck_risk_rule_version"),
        Index("ix_risk_rule_group_enabled", "rule_group_code", "is_enabled"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    rule_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_group_code: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    applicable_order_types: Mapped[list[str]] = mapped_column(mysql.JSON, nullable=False)
    condition_json: Mapped[dict[str, Any]] = mapped_column(mysql.JSON, nullable=False)
    risk_score: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    rule_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("1")
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_risk_assessment_order_id"),
        CheckConstraint("raw_score >= 0", name="ck_assessment_raw_score"),
        CheckConstraint(
            "model_probability IS NULL OR (model_probability >= 0 AND model_probability <= 1)",
            name="ck_assessment_model_probability",
        ),
        CheckConstraint(
            "model_score IS NULL OR (model_score >= 0 AND model_score <= 100)",
            name="ck_assessment_model_score",
        ),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_assessment_score"),
        Index("ix_assessment_decision_time", "decision", "evaluated_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    assessment_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    raw_score: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    model_probability: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 8), nullable=True
    )
    model_score: Mapped[int | None] = mapped_column(
        mysql.TINYINT(unsigned=True), nullable=True
    )
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_score: Mapped[int] = mapped_column(mysql.TINYINT(unsigned=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class RiskHit(Base):
    __tablename__ = "risk_hit"
    __table_args__ = (
        UniqueConstraint("assessment_id", "rule_id", name="uq_risk_hit_assessment_rule"),
        Index("ix_risk_hit_rule_code", "rule_code_snapshot"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    hit_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    assessment_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey(
            "risk_assessment.assessment_id", ondelete="RESTRICT", onupdate="CASCADE"
        ),
        nullable=False,
    )
    rule_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("risk_rule.rule_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    rule_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    score_snapshot: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), nullable=False
    )
    condition_snapshot: Mapped[dict[str, Any]] = mapped_column(mysql.JSON, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(mysql.JSON, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class ReviewCase(Base):
    __tablename__ = "review_case"
    __table_args__ = (
        UniqueConstraint("case_no", name="uq_review_case_no"),
        UniqueConstraint("assessment_id", name="uq_review_case_assessment_id"),
        Index("ix_review_case_order_id", "order_id"),
        Index("ix_review_case_status_created", "status", "created_at"),
        Index("ix_review_case_reviewer", "reviewer"),
        Index("ix_review_case_reviewed_at", "reviewed_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    case_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    case_no: Mapped[str] = mapped_column(String(32), nullable=False)
    order_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    assessment_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey(
            "risk_assessment.assessment_id", ondelete="RESTRICT", onupdate="CASCADE"
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'PENDING'")
    )
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    lock_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_operator", "operator"),
        Index("ix_audit_log_action_created", "action", "created_at"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_request_id", "request_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    log_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(mysql.JSON, nullable=True)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(mysql.JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class StaffUser(Base):
    __tablename__ = "staff_user"
    __table_args__ = (
        UniqueConstraint("username", name="uq_staff_user_username"),
        Index("ix_staff_user_active", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    staff_user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    session_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("1")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Role(Base):
    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("role_code", name="uq_role_code"),
        Index("ix_role_system", "is_system"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    role_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    role_code: Mapped[str] = mapped_column(String(50), nullable=False)
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = (
        UniqueConstraint("permission_code", name="uq_permission_code"),
        Index("ix_permission_module", "module"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    permission_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    permission_code: Mapped[str] = mapped_column(String(80), nullable=False)
    permission_name: Mapped[str] = mapped_column(String(100), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class StaffUserRole(Base):
    __tablename__ = "staff_user_role"
    __table_args__ = (
        UniqueConstraint("staff_user_id", name="uq_staff_user_role_staff_user_id"),
        Index("ix_staff_user_role_role_id", "role_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    staff_user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("staff_user.staff_user_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("role.role_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    assigned_by: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("staff_user.staff_user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )


class RolePermission(Base):
    __tablename__ = "role_permission"
    __table_args__ = (
        Index("ix_role_permission_permission_id", "permission_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    role_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("role.role_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("permission.permission_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
