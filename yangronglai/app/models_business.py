"""ORM mappings for the eight bank-owned business tables.

These tables are the source-of-truth inputs used by feature computation.  They
do not contain risk decisions; risk data is intentionally isolated in
``models_risk.py``.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class UserInfo(Base):
    """Customer identity, KYC and credit overview."""

    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    id_card_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    credit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    kyc_level: Mapped[str] = mapped_column(String(16), nullable=False, default="KYC1")

    __table_args__ = (
        Index("idx_user_info_register_at", "register_at"),
        Index("idx_user_info_credit_score", "credit_score"),
    )


class BankCard(Base):
    """Debit or credit card owned by a customer."""

    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    card_no_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    bank_code: Mapped[str] = mapped_column(String(32), nullable=False)
    card_type: Mapped[str] = mapped_column(String(16), nullable=False)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_bank_card_user_id", "user_id"),
        Index("idx_bank_card_status", "status"),
    )


class Transaction(Base):
    """Card purchase or account transfer.

    The physical name avoids the SQL reserved word ``TRANSACTION`` while the
    domain class keeps the name used in the project brief.
    """

    __tablename__ = "bank_transaction"

    txn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    from_card: Mapped[str | None] = mapped_column(String(64))
    to_card: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    txn_type: Mapped[str] = mapped_column(String(24), nullable=False, default="TRANSFER")
    device_id: Mapped[str | None] = mapped_column(String(128))
    ip: Mapped[str | None] = mapped_column(String(64))
    geo: Mapped[str | None] = mapped_column(String(128))
    merchant_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCESS")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_transaction_user_time", "user_id", "occurred_at"),
        Index("idx_transaction_to_card_time", "to_card", "occurred_at"),
        Index("idx_transaction_device", "device_id"),
        Index("idx_transaction_ip", "ip"),
    )


class LoanApplication(Base):
    """Loan application submitted to this or an external institution."""

    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    institution_code: Mapped[str] = mapped_column(String(32), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128))
    ip: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_loan_user_time", "user_id", "applied_at"),
        Index("idx_loan_institution", "institution_code"),
    )


class LoginLog(Base):
    """Customer authentication attempt."""

    __tablename__ = "login_log"

    login_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128))
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    geo: Mapped[str | None] = mapped_column(String(128))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    login_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_login_user_time", "user_id", "login_at"),
        Index("idx_login_device", "device_id"),
        Index("idx_login_ip", "ip"),
    )


class DeviceFingerprint(Base):
    """Many-to-many observation between a physical device and customers."""

    __tablename__ = "device_fingerprint"

    record_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    os: Mapped[str | None] = mapped_column(String(64))
    browser: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="uq_device_user"),
        Index("idx_device_fingerprint_device", "device_id"),
        Index("idx_device_fingerprint_user", "user_id"),
    )


class IpGeoLocation(Base):
    """IP intelligence snapshot used by login and transaction checks."""

    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    country: Mapped[str | None] = mapped_column(String(64))
    province: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(64))
    isp: Mapped[str | None] = mapped_column(String(100))
    is_proxy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class BlacklistExtra(Base):
    """Bank-specific blacklist for device, IP, card and identity hashes."""

    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("entry_type", "value", name="uq_blacklist_extra_type_value"),
        Index("idx_blacklist_extra_expire", "expire_at"),
    )


__all__ = [
    "UserInfo",
    "BankCard",
    "Transaction",
    "LoanApplication",
    "LoginLog",
    "DeviceFingerprint",
    "IpGeoLocation",
    "BlacklistExtra",
]
