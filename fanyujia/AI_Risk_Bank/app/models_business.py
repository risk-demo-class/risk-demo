"""银行风控教学场景的 8 张业务 ORM 表。"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    __tablename__ = "bank_user_info"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    id_card_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    credit_score: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    register_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    kyc_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0, nullable=False)
    home_geo: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="正常", nullable=False)


class BankCard(Base):
    __tablename__ = "bank_card"
    card_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    card_no_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    open_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class BankTransaction(Base):
    __tablename__ = "bank_transaction"
    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_card_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    to_card_hash: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    payee_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    geo: Mapped[Optional[str]] = mapped_column(String(100))
    txn_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="成功", nullable=False)


class LoanApplication(Base):
    __tablename__ = "loan_application"
    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    apply_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="待审批", nullable=False)


class LoginLog(Base):
    __tablename__ = "login_log"
    login_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    geo: Mapped[Optional[str]] = mapped_column(String(100))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    login_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, index=True)


class DeviceFingerprint(Base):
    __tablename__ = "device_fingerprint"
    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    os: Mapped[Optional[str]] = mapped_column(String(50))
    browser: Mapped[Optional[str]] = mapped_column(String(50))
    __table_args__ = (UniqueConstraint("device_id", "user_id", name="uq_device_user"), Index("idx_device_user", "device_id", "user_id"))


class IpGeoLocation(Base):
    __tablename__ = "ip_geo_location"
    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    country: Mapped[str] = mapped_column(String(50), default="中国", nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50))
    city: Mapped[Optional[str]] = mapped_column(String(50))
    isp: Mapped[Optional[str]] = mapped_column(String(100))
    is_proxy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PayeeRelationship(Base):
    __tablename__ = "payee_relationship"
    relation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    payee_id: Mapped[str] = mapped_column(String(50), nullable=False)
    payee_card_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    first_txn_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    last_txn_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    txn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "payee_id", name="uq_user_payee"), Index("idx_payee_user", "user_id", "payee_id"))
