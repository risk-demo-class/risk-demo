"""银行风控业务表 ORM。

业务边界固定为信用卡、贷款、转账、登录四类事件。风控核心九张表仍在
models_risk.py 中复用；本文件只描述银行业务事实，不保存风控结论。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    """银行客户/KYC 主档。敏感标识只保存不可逆哈希。"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    id_card_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    credit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kyc_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    home_city: Mapped[str] = mapped_column(String(50), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="正常")


class BankCard(Base):
    """银行卡。card_no_hash 代替明文卡号。"""
    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    card_no_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="正常")


class BankTransaction(Base):
    """信用卡消费与转账共用交易流水。"""
    __tablename__ = "bank_transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    txn_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    from_card: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    to_card: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    geo: Mapped[str] = mapped_column(String(50), nullable=False)
    merchant_category: Mapped[Optional[str]] = mapped_column(String(50))
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    txn_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class LoanApplication(Base):
    """贷款申请。institution_code 用于识别多头借贷。"""
    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    institution_code: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    apply_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="待审批")


class LoginLog(Base):
    """网上银行/手机银行登录日志。"""
    __tablename__ = "login_log"

    login_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    geo: Mapped[str] = mapped_column(String(50), nullable=False)
    success: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(100))
    login_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class DeviceFingerprint(Base):
    """设备指纹与客户关系，同一设备可关联多个客户。"""
    __tablename__ = "device_fingerprint"
    __table_args__ = (UniqueConstraint("device_id", "user_id", name="uk_device_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    os: Mapped[str] = mapped_column(String(40), nullable=False)
    browser: Mapped[str] = mapped_column(String(40), nullable=False)
    trusted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class IpGeoLocation(Base):
    """IP 画像与代理/Tor 情报。"""
    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(45), primary_key=True)
    country: Mapped[str] = mapped_column(String(50), nullable=False)
    province: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    isp: Mapped[str] = mapped_column(String(80), nullable=False)
    is_proxy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_tor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BlacklistExtra(Base):
    """外部银行威胁情报名单；运营名单仍使用核心 risk_blacklist。"""
    __tablename__ = "blacklist_extra"
    __table_args__ = (UniqueConstraint("entry_type", "entry_value", name="uk_extra_type_value"),)

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entry_value: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="内部名单")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
