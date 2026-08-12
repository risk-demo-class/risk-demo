"""SQLAlchemy 2.x models for the PingPong cross-border risk demo database.

The schema is intentionally hybrid:
- normalized master data for identity, store, VA, counterparty and account links;
- denormalized keys/snapshots on payment facts for fast rolling feature queries;
- append-oriented event, ledger and audit tables for point-in-time reproducibility.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


IdType = BIGINT(unsigned=True)
MoneyType = Numeric(20, 4)
RateType = Numeric(20, 10)
ScoreType = Numeric(8, 4)
TimestampType = DATETIME(fsp=6)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )


class Partner(Base, TimestampMixin):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    partner_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    partner_name: Mapped[str] = mapped_column(String(128), nullable=False)
    partner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    api_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    customers: Mapped[list[Customer]] = relationship(back_populates="partner")

    __table_args__ = (
        CheckConstraint("risk_tier IN ('LOW','MEDIUM','HIGH')", name="risk_tier"),
        Index("ix_partners_type_status", "partner_type", "status"),
    )


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    customer_location: Mapped[str] = mapped_column(String(2), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name_en: Mapped[str | None] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    company_url: Mapped[str | None] = mapped_column(String(512))
    declared_business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    declared_industry_code: Mapped[str | None] = mapped_column(String(32))
    export_country_list: Mapped[list[str] | None] = mapped_column(JSON)
    expected_currencies: Mapped[list[str] | None] = mapped_column(JSON)
    expected_monthly_volume_usd: Mapped[Decimal | None] = mapped_column(MoneyType)
    expected_monthly_count: Mapped[int | None] = mapped_column(Integer)
    kyc_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    account_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    first_approved_at: Mapped[datetime | None] = mapped_column(TimestampType)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(TimestampType)

    partner: Mapped[Partner] = relationship(back_populates="customers")
    person_roles: Mapped[list[CustomerPersonRole]] = relationship(back_populates="customer")
    stores: Mapped[list[Store]] = relationship(back_populates="customer")
    virtual_accounts: Mapped[list[VirtualAccount]] = relationship(back_populates="customer")
    inbound_payments: Mapped[list[InboundPayment]] = relationship(back_populates="customer")
    payouts: Mapped[list[Payout]] = relationship(back_populates="customer")

    __table_args__ = (
        UniqueConstraint("partner_id", "registration_number_hash"),
        CheckConstraint(
            "customer_type IN ('ENTERPRISE','INDIVIDUAL')", name="customer_type"
        ),
        CheckConstraint(
            "kyc_status IN ('PENDING','APPROVED','DECLINED')", name="kyc_status"
        ),
        Index("ix_customers_partner_kyc", "partner_id", "kyc_status"),
        Index("ix_customers_risk_status", "risk_tier", "account_status"),
        Index("ix_customers_business_type", "declared_business_type"),
        Index("ix_customers_reg_hash", "registration_number_hash"),
    )


class Person(Base, TimestampMixin):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    person_ref: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name_en: Mapped[str | None] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(2))
    residence_country: Mapped[str | None] = mapped_column(String(2))
    id_type: Mapped[str | None] = mapped_column(String(32))
    id_country: Mapped[str | None] = mapped_column(String(2))
    id_number_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    phone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    email_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    pep_status: Mapped[str] = mapped_column(String(16), nullable=False, default="CLEAR")
    sanctions_status: Mapped[str] = mapped_column(String(16), nullable=False, default="CLEAR")

    customer_roles: Mapped[list[CustomerPersonRole]] = relationship(back_populates="person")

    __table_args__ = (
        Index("ix_persons_name_dob", "normalized_name", "date_of_birth"),
        Index("ix_persons_screening", "sanctions_status", "pep_status"),
    )


class CustomerPersonRole(Base):
    __tablename__ = "customer_person_roles"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    role_type: Mapped[str] = mapped_column(String(24), nullable=False)
    ownership_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    control_type: Mapped[str | None] = mapped_column(String(32))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="DECLARED")

    customer: Mapped[Customer] = relationship(back_populates="person_roles")
    person: Mapped[Person] = relationship(back_populates="customer_roles")

    __table_args__ = (
        UniqueConstraint("customer_id", "person_id", "role_type"),
        Index("ix_customer_person_role_person", "person_id", "role_type"),
        Index("ix_customer_person_role_customer", "customer_id", "role_type"),
    )


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(16), nullable=False)
    os_name: Mapped[str | None] = mapped_column(String(32))
    browser_name: Mapped[str | None] = mapped_column(String(32))
    is_emulator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_rooted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("persons.id", ondelete="SET NULL")
    )
    device_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("devices.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    event_time: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    event_date: Mapped[date] = mapped_column(
        Date, Computed("DATE(event_time)", persisted=True), nullable=False
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    ip_country: Mapped[str | None] = mapped_column(String(2))
    asn: Mapped[int | None] = mapped_column(Integer)
    vpn_proxy_tor_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_new_device: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_auth_customer_time", "customer_id", "event_time"),
        Index("ix_auth_device_time", "device_id", "event_time"),
        Index("ix_auth_type_time", "event_type", "event_time"),
        Index("ix_auth_partner_date", "partner_id", "event_date"),
    )


class Store(Base, TimestampMixin):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    seller_id: Mapped[str | None] = mapped_column(String(128))
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    store_url: Mapped[str | None] = mapped_column(String(512))
    category_code: Mapped[str | None] = mapped_column(String(32))
    auth_type: Mapped[str | None] = mapped_column(String(16))
    auth_status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNAUTHORIZED")
    auth_credential_fingerprint: Mapped[str | None] = mapped_column(String(64))
    authorized_at: Mapped[datetime | None] = mapped_column(TimestampType)
    auth_expires_at: Mapped[datetime | None] = mapped_column(TimestampType)
    last_order_sync_at: Mapped[datetime | None] = mapped_column(TimestampType)
    ownership_match_score: Mapped[Decimal | None] = mapped_column(ScoreType)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")

    customer: Mapped[Customer] = relationship(back_populates="stores")
    va_links: Mapped[list[StoreVirtualAccountLink]] = relationship(back_populates="store")

    __table_args__ = (
        UniqueConstraint("platform", "seller_id"),
        Index("ix_stores_customer_platform", "customer_id", "platform"),
        Index("ix_stores_partner_auth", "partner_id", "auth_status"),
        Index("ix_stores_auth_fingerprint", "auth_credential_fingerprint"),
    )


class VirtualAccount(Base, TimestampMixin):
    __tablename__ = "virtual_accounts"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    va_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    purpose_code: Mapped[str] = mapped_column(String(4), nullable=False)
    purpose_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    bank_country: Mapped[str] = mapped_column(String(2), nullable=False)
    rail: Mapped[str] = mapped_column(String(24), nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    account_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    opened_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    first_credit_at: Mapped[datetime | None] = mapped_column(TimestampType)
    last_credit_at: Mapped[datetime | None] = mapped_column(TimestampType)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")

    customer: Mapped[Customer] = relationship(back_populates="virtual_accounts")
    store_links: Mapped[list[StoreVirtualAccountLink]] = relationship(
        back_populates="virtual_account"
    )

    __table_args__ = (
        Index("ix_va_customer_currency", "customer_id", "currency"),
        Index("ix_va_partner_purpose", "partner_id", "purpose_code"),
        Index("ix_va_status_country", "status", "bank_country"),
    )


class StoreVirtualAccountLink(Base):
    __tablename__ = "store_virtual_account_links"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    virtual_account_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("virtual_accounts.id", ondelete="CASCADE"), nullable=False
    )
    linked_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(TimestampType)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    store: Mapped[Store] = relationship(back_populates="va_links")
    virtual_account: Mapped[VirtualAccount] = relationship(back_populates="store_links")

    __table_args__ = (
        UniqueConstraint("store_id", "virtual_account_id"),
        Index("ix_store_va_va_status", "virtual_account_id", "status"),
    )


class Counterparty(Base, TimestampMixin):
    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    counterparty_ref: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    counterparty_type: Mapped[str] = mapped_column(String(24), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    registration_or_id_hash: Mapped[str | None] = mapped_column(String(64))
    industry_code: Mapped[str | None] = mapped_column(String(32))
    sanctions_status: Mapped[str] = mapped_column(String(16), nullable=False, default="CLEAR")
    external_risk_label: Mapped[str | None] = mapped_column(String(32))
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)

    __table_args__ = (
        Index("ix_counterparty_name_country", "normalized_name", "country_code"),
        Index("ix_counterparty_label_score", "external_risk_label", "risk_score"),
        Index("ix_counterparty_reg_hash", "registration_or_id_hash"),
    )


class BankAccount(Base, TimestampMixin):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    account_ref: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    owner_type: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE")
    )
    counterparty_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("counterparties.id", ondelete="CASCADE")
    )
    holder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_holder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    holder_type: Mapped[str] = mapped_column(String(16), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_country: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    account_number_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    account_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ownership_check_result: Mapped[str] = mapped_column(String(16), nullable=False)
    name_match_score: Mapped[Decimal | None] = mapped_column(ScoreType)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="APPROVED")
    first_used_at: Mapped[datetime | None] = mapped_column(TimestampType)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "(customer_id IS NOT NULL) <> (counterparty_id IS NOT NULL)",
            name="single_owner",
        ),
        Index("ix_bank_accounts_customer_status", "customer_id", "status"),
        Index("ix_bank_accounts_counterparty", "counterparty_id"),
        Index("ix_bank_accounts_country_risk", "bank_country", "risk_score"),
    )


class TradeOrder(Base, TimestampMixin):
    __tablename__ = "trade_orders"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    trade_order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("stores.id", ondelete="SET NULL")
    )
    buyer_counterparty_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("counterparties.id", ondelete="RESTRICT"), nullable=False
    )
    business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    settlement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_code: Mapped[str] = mapped_column(String(16), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    reserved_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    approved_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    order_time: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    order_date: Mapped[date] = mapped_column(
        Date, Computed("DATE(order_time)", persisted=True), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(String(16), nullable=False)
    trading_terms: Mapped[str | None] = mapped_column(String(16))
    declaration_no: Mapped[str | None] = mapped_column(String(128))
    is_new_buyer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category_code: Mapped[str | None] = mapped_column(String(32))
    consignee_country_code: Mapped[str | None] = mapped_column(String(2))
    buyer_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_country_snapshot: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUBMITTED")
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)

    allocations: Mapped[list[InboundOrderAllocation]] = relationship(back_populates="trade_order")

    __table_args__ = (
        UniqueConstraint("partner_id", "trade_order_no"),
        Index("ix_trade_order_customer_time", "customer_id", "order_time"),
        Index("ix_trade_order_buyer_time", "buyer_counterparty_id", "order_time"),
        Index("ix_trade_order_declaration", "declaration_no"),
        Index("ix_trade_order_business_date", "business_type", "order_date"),
        CheckConstraint("total_amount > 0", name="positive_total"),
        CheckConstraint("reserved_amount >= 0", name="nonnegative_reserved"),
        CheckConstraint("approved_amount >= 0", name="nonnegative_approved"),
    )


class TradeDocument(Base, TimestampMixin):
    __tablename__ = "trade_documents"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    trade_order_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("trade_orders.id", ondelete="SET NULL")
    )
    document_type: Mapped[str] = mapped_column(String(24), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(128))
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issued_at: Mapped[date | None] = mapped_column(Date)
    issuer_name: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal | None] = mapped_column(MoneyType)
    currency: Mapped[str | None] = mapped_column(String(3))
    ocr_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    tamper_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")

    __table_args__ = (
        Index("ix_trade_doc_order_type", "trade_order_id", "document_type"),
        Index("ix_trade_doc_customer_hash", "customer_id", "file_hash"),
        Index("ix_trade_doc_number_type", "document_number", "document_type"),
    )


class InboundPayment(Base, TimestampMixin):
    __tablename__ = "inbound_payments"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    virtual_account_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("virtual_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("stores.id", ondelete="SET NULL")
    )
    payer_counterparty_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("counterparties.id", ondelete="RESTRICT"), nullable=False
    )
    payer_bank_account_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("bank_accounts.id", ondelete="SET NULL")
    )
    business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    received_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    received_date: Mapped[date] = mapped_column(
        Date, Computed("DATE(received_at)", persisted=True), nullable=False
    )
    value_date: Mapped[date | None] = mapped_column(Date)
    end_to_end_id: Mapped[str | None] = mapped_column(String(64))
    uetr: Mapped[str | None] = mapped_column(String(64))
    origin_country: Mapped[str] = mapped_column(String(2), nullable=False)
    rail: Mapped[str] = mapped_column(String(24), nullable=False)
    remittance_text: Mapped[str | None] = mapped_column(String(512))
    is_third_party_payment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    third_party_reason: Mapped[str | None] = mapped_column(String(32))
    is_first_payer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inbound_status: Mapped[str] = mapped_column(String(24), nullable=False)
    temp_posted_at: Mapped[datetime | None] = mapped_column(TimestampType)
    available_at: Mapped[datetime | None] = mapped_column(TimestampType)
    refunded_at: Mapped[datetime | None] = mapped_column(TimestampType)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)
    risk_tier_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    data_quality_flags: Mapped[list[str] | None] = mapped_column(JSON)

    customer: Mapped[Customer] = relationship(back_populates="inbound_payments")
    audits: Mapped[list[InboundAudit]] = relationship(back_populates="inbound_payment")
    allocations: Mapped[list[InboundOrderAllocation]] = relationship(back_populates="inbound_payment")

    __table_args__ = (
        UniqueConstraint("partner_id", "partner_reference"),
        Index("ix_inbound_customer_time", "customer_id", "received_at"),
        Index("ix_inbound_payer_time", "payer_counterparty_id", "received_at"),
        Index("ix_inbound_va_time", "virtual_account_id", "received_at"),
        Index("ix_inbound_partner_date", "partner_id", "received_date"),
        Index("ix_inbound_customer_status_time", "customer_id", "inbound_status", "received_at"),
        Index("ix_inbound_business_date", "business_type", "received_date"),
        Index("ix_inbound_origin_date", "origin_country", "received_date"),
        Index("ix_inbound_uetr", "uetr"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("amount_usd > 0", name="positive_amount_usd"),
    )


class InboundOrderAllocation(Base):
    __tablename__ = "inbound_order_allocations"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    inbound_payment_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("inbound_payments.id", ondelete="CASCADE"), nullable=False
    )
    trade_order_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("trade_orders.id", ondelete="RESTRICT"), nullable=False
    )
    allocated_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    allocation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(TimestampType)

    inbound_payment: Mapped[InboundPayment] = relationship(back_populates="allocations")
    trade_order: Mapped[TradeOrder] = relationship(back_populates="allocations")

    __table_args__ = (
        UniqueConstraint("inbound_payment_id", "trade_order_id"),
        Index("ix_allocation_order_status", "trade_order_id", "allocation_status"),
        CheckConstraint("allocated_amount > 0", name="positive_amount"),
    )


class InboundAudit(Base):
    __tablename__ = "inbound_audits"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    inbound_payment_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("inbound_payments.id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(IdType, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    fail_reason: Mapped[str | None] = mapped_column(String(255))
    submitted_by_type: Mapped[str] = mapped_column(String(16), nullable=False)
    submitted_by_id: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    evidence_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rule_hits: Mapped[list[str] | None] = mapped_column(JSON)
    decision_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)

    inbound_payment: Mapped[InboundPayment] = relationship(back_populates="audits")

    __table_args__ = (
        UniqueConstraint("inbound_payment_id", "attempt_no"),
        Index("ix_audit_customer_time", "customer_id", "submitted_at"),
        Index("ix_audit_partner_status_time", "partner_id", "status", "submitted_at"),
        Index("ix_audit_reason", "reason_code"),
    )


class LedgerAccount(Base, TimestampMixin):
    __tablename__ = "ledger_accounts"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    ledger_account_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    frozen_balance: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")

    entries: Mapped[list[LedgerEntry]] = relationship(back_populates="ledger_account")

    __table_args__ = (
        UniqueConstraint("customer_id", "account_type", "currency"),
        Index("ix_ledger_account_partner_type", "partner_id", "account_type"),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    entry_group_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ledger_account_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(IdType, nullable=False)
    direction: Mapped[str] = mapped_column(String(2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    business_type: Mapped[str] = mapped_column(String(24), nullable=False)
    business_ref_type: Mapped[str] = mapped_column(String(24), nullable=False)
    business_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fund_source_transaction_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("inbound_payments.id", ondelete="SET NULL")
    )
    booked_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    booked_date: Mapped[date] = mapped_column(
        Date, Computed("DATE(booked_at)", persisted=True), nullable=False
    )
    balance_after: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    reversal_of_entry_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("ledger_entries.id", ondelete="SET NULL")
    )

    ledger_account: Mapped[LedgerAccount] = relationship(back_populates="entries")

    __table_args__ = (
        Index("ix_ledger_customer_time", "customer_id", "booked_at"),
        Index("ix_ledger_account_time", "ledger_account_id", "booked_at"),
        Index("ix_ledger_group", "entry_group_id"),
        Index("ix_ledger_business_ref", "business_ref_type", "business_ref_id"),
        Index("ix_ledger_partner_date", "partner_id", "booked_date"),
        CheckConstraint("direction IN ('DR','CR')", name="direction"),
        CheckConstraint("amount > 0", name="positive_amount"),
    )


class FxOrder(Base, TimestampMixin):
    __tablename__ = "fx_orders"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    fx_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    sell_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sell_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    buy_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    buy_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(RateType, nullable=False)
    quote_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_inbound_payment_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("inbound_payments.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)

    __table_args__ = (
        Index("ix_fx_customer_time", "customer_id", "requested_at"),
        Index("ix_fx_pair_time", "sell_currency", "buy_currency", "requested_at"),
        CheckConstraint("sell_amount > 0 AND buy_amount > 0", name="positive_amounts"),
    )


class Payout(Base, TimestampMixin):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    payout_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    beneficiary_bank_account_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("bank_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    source_inbound_payment_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("inbound_payments.id", ondelete="SET NULL")
    )
    fx_order_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("fx_orders.id", ondelete="SET NULL")
    )
    payout_type: Mapped[str] = mapped_column(String(16), nullable=False)
    pay_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    pay_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    fx_rate: Mapped[Decimal | None] = mapped_column(RateType)
    payer_name: Mapped[str | None] = mapped_column(String(255))
    charges_indicator: Mapped[str | None] = mapped_column(String(3))
    trade_code: Mapped[str | None] = mapped_column(String(16))
    remark: Mapped[str | None] = mapped_column(String(255))
    requested_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    requested_date: Mapped[date] = mapped_column(
        Date, Computed("DATE(requested_at)", persisted=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(TimestampType)
    completed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(128))
    is_new_beneficiary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recent_security_event_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seconds_since_inbound: Mapped[int | None] = mapped_column(BigInteger)
    balance_drain_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)

    customer: Mapped[Customer] = relationship(back_populates="payouts")

    __table_args__ = (
        UniqueConstraint("partner_id", "partner_order_id"),
        Index("ix_payout_customer_time", "customer_id", "requested_at"),
        Index("ix_payout_beneficiary_time", "beneficiary_bank_account_id", "requested_at"),
        Index("ix_payout_partner_date", "partner_id", "requested_date"),
        Index("ix_payout_customer_status_time", "customer_id", "status", "requested_at"),
        Index("ix_payout_source_inbound", "source_inbound_payment_id"),
        CheckConstraint("payout_type IN ('WITHDRAW','PAY')", name="payout_type"),
        CheckConstraint("pay_amount > 0 AND target_amount > 0", name="positive_amounts"),
    )


class RiskRule(Base, TimestampMixin):
    __tablename__ = "risk_rules"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    fraud_scenario: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    is_veto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_refs: Mapped[list[str] | None] = mapped_column(JSON)
    effective_from: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(TimestampType)

    __table_args__ = (
        Index("ix_risk_rule_stage_enabled", "stage", "is_enabled", "priority"),
        Index("ix_risk_rule_category_severity", "category", "severity"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="score_range"),
    )


class RiskBlacklist(Base, TimestampMixin):
    __tablename__ = "risk_blacklist"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    blacklist_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(String(512))
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="HIGH")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="MANUAL")
    source_refs: Mapped[list[str] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TimestampType)
    hit_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(TimestampType)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="risk-operator")
    removed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    removed_by: Mapped[str | None] = mapped_column(String(64))
    removed_reason: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_value", name="uq_blacklist_entity_value"),
        Index("ix_blacklist_active_lookup", "entity_type", "normalized_value", "is_active"),
        Index("ix_blacklist_status_expiry", "is_active", "expires_at", "severity"),
        Index("ix_blacklist_reason_created", "reason_code", "created_at"),
        CheckConstraint(
            "entity_type IN ('CUSTOMER','COUNTERPARTY','BANK_ACCOUNT','VIRTUAL_ACCOUNT','DEVICE','DOCUMENT_HASH','COUNTRY')",
            name="entity_type",
        ),
        CheckConstraint("severity IN ('MEDIUM','HIGH','CRITICAL')", name="severity"),
        CheckConstraint("source IN ('MANUAL','CASE','SCREENING','EXTERNAL')", name="source"),
        CheckConstraint("hit_count >= 0", name="hit_count_non_negative"),
    )


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    risk_domain: Mapped[str] = mapped_column(String(24), nullable=False)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("customers.id", ondelete="CASCADE")
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String(24))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    event_date: Mapped[date] = mapped_column(
        Date, Computed("DATE(occurred_at)", persisted=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    causation_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    source_system: Mapped[str] = mapped_column(String(48), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=0)
    labels: Mapped[list[str] | None] = mapped_column(JSON)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_risk_event_customer_time", "customer_id", "occurred_at"),
        Index("ix_risk_event_subject_time", "subject_type", "subject_id", "occurred_at"),
        Index("ix_risk_event_type_time", "event_type", "occurred_at"),
        Index("ix_risk_event_partner_date", "partner_id", "event_date"),
        Index("ix_risk_event_domain_time", "risk_domain", "occurred_at"),
        Index("ix_risk_event_correlation", "correlation_id"),
    )


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    risk_event_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("risk_events.id", ondelete="SET NULL")
    )
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(IdType)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_domain: Mapped[str] = mapped_column(String(24), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(ScoreType, nullable=False)
    rule_hits: Mapped[list[str] | None] = mapped_column(JSON)
    model_outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TimestampType)
    manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_by: Mapped[str | None] = mapped_column(String(64))
    override_reason: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        Index("ix_decision_customer_time", "customer_id", "decided_at"),
        Index("ix_decision_subject", "subject_type", "subject_id", "decided_at"),
        Index("ix_decision_action_time", "decision", "decided_at"),
    )


class RiskCase(Base, TimestampMixin):
    __tablename__ = "risk_cases"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_id: Mapped[int] = mapped_column(IdType, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(IdType)
    case_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(TimestampType)
    closed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    assignee: Mapped[str | None] = mapped_column(String(64))
    disposition: Mapped[str | None] = mapped_column(String(32))
    label_confidence: Mapped[Decimal | None] = mapped_column(ScoreType)
    loss_amount_usd: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    recovered_amount_usd: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text)

    entity_links: Mapped[list[CaseEntity]] = relationship(back_populates="risk_case")

    __table_args__ = (
        Index("ix_case_customer_status", "customer_id", "status"),
        Index("ix_case_partner_priority", "partner_id", "priority", "opened_at"),
        Index("ix_case_disposition", "disposition", "closed_at"),
    )


class CaseEntity(Base):
    __tablename__ = "case_entities"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    risk_case_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    added_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    risk_case: Mapped[RiskCase] = relationship(back_populates="entity_links")

    __table_args__ = (
        UniqueConstraint("risk_case_id", "entity_type", "entity_id", "relation_type"),
        Index("ix_case_entity_lookup", "entity_type", "entity_id"),
    )


class EntityRelation(Base):
    __tablename__ = "entity_relations"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    src_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    src_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dst_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dst_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(TimestampType)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(ScoreType, nullable=False, default=100)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint(
            "src_entity_type",
            "src_entity_id",
            "dst_entity_type",
            "dst_entity_id",
            "relation_type",
        ),
        Index("ix_relation_src", "src_entity_type", "src_entity_id", "relation_type"),
        Index("ix_relation_dst", "dst_entity_type", "dst_entity_id", "relation_type"),
        Index("ix_relation_type_time", "relation_type", "valid_from"),
    )


ALL_MODELS = [
    Partner,
    Customer,
    Person,
    CustomerPersonRole,
    Device,
    AuthEvent,
    Store,
    VirtualAccount,
    StoreVirtualAccountLink,
    Counterparty,
    BankAccount,
    TradeOrder,
    TradeDocument,
    InboundPayment,
    InboundOrderAllocation,
    InboundAudit,
    LedgerAccount,
    LedgerEntry,
    FxOrder,
    Payout,
    RiskRule,
    RiskBlacklist,
    RiskEvent,
    RiskDecision,
    RiskCase,
    CaseEntity,
    EntityRelation,
]
