"""8 张银行业务表 ORM。

这些表保存风控决策发生之前已经存在的权威业务数据。特征计算必须从这里
读取金额、设备、IP、时间和归属关系，不能直接相信调用方传入的 event_data。
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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

from app.models import Base, enum_type


class KycLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class CustomerStatus(StrEnum):
    NORMAL = "NORMAL"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class AccountType(StrEnum):
    SAVING = "SAVING"
    CURRENT = "CURRENT"
    LOAN = "LOAN"


class AccountStatus(StrEnum):
    NORMAL = "NORMAL"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class CardType(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class CardStatus(StrEnum):
    NORMAL = "NORMAL"
    FROZEN = "FROZEN"
    LOST = "LOST"
    CLOSED = "CLOSED"


class TransactionType(StrEnum):
    TRANSFER = "TRANSFER"
    CARD_PAYMENT = "CARD_PAYMENT"


class TransactionChannel(StrEnum):
    APP = "APP"
    WEB = "WEB"
    ATM = "ATM"
    POS = "POS"


class TransactionStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class LoanStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CustomerInfo(Base):
    __tablename__ = "customer_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="客户ID")
    name_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="姓名哈希")
    id_card_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="身份证哈希"
    )
    mobile_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="手机号哈希")
    credit_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="模拟信用分")
    kyc_level: Mapped[KycLevel] = mapped_column(
        enum_type(KycLevel, "kyc_level_enum"), nullable=False, comment="身份核验等级"
    )
    monthly_income: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, comment="月收入(演示数据)"
    )
    home_city: Mapped[str] = mapped_column(String(50), nullable=False, comment="常驻城市")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    status: Mapped[CustomerStatus] = mapped_column(
        enum_type(CustomerStatus, "customer_status_enum"),
        nullable=False,
        default=CustomerStatus.NORMAL,
        comment="客户状态",
    )

    __table_args__ = (
        CheckConstraint("credit_score BETWEEN 300 AND 850", name="credit_score_range"),
        CheckConstraint("monthly_income >= 0", name="monthly_income_non_negative"),
        Index("idx_customer_mobile_hash", "mobile_hash"),
        Index("idx_customer_register_at", "register_at"),
    )


class BankAccount(Base):
    __tablename__ = "bank_account"

    account_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="账户ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_info.user_id"), nullable=False, index=True, comment="账户所有人"
    )
    account_no_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="账号哈希"
    )
    account_type: Mapped[AccountType] = mapped_column(
        enum_type(AccountType, "account_type_enum"), nullable=False, comment="账户类型"
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0, comment="账面余额")
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=0, comment="可用余额"
    )
    home_branch: Mapped[str] = mapped_column(String(100), nullable=False, comment="开户网点")
    open_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开户时间")
    status: Mapped[AccountStatus] = mapped_column(
        enum_type(AccountStatus, "account_status_enum"),
        nullable=False,
        default=AccountStatus.NORMAL,
        comment="账户状态",
    )

    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint("available_balance >= 0", name="available_balance_non_negative"),
        Index("idx_bank_account_open_at", "open_at"),
    )


class BankCard(Base):
    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="卡ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_info.user_id"), nullable=False, index=True, comment="持卡人"
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("bank_account.account_id"), nullable=False, index=True, comment="关联账户"
    )
    card_no_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="卡号哈希"
    )
    card_type: Mapped[CardType] = mapped_column(
        enum_type(CardType, "card_type_enum"), nullable=False, comment="卡类型"
    )
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, comment="信用额度"
    )
    available_limit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, comment="可用额度"
    )
    issue_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="发卡时间")
    status: Mapped[CardStatus] = mapped_column(
        enum_type(CardStatus, "card_status_enum"),
        nullable=False,
        default=CardStatus.NORMAL,
        comment="卡状态",
    )

    __table_args__ = (
        CheckConstraint("credit_limit >= 0", name="credit_limit_non_negative"),
        CheckConstraint("available_limit >= 0", name="available_limit_non_negative"),
    )


class BankTransaction(Base):
    __tablename__ = "bank_transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_info.user_id"), nullable=False, index=True, comment="发起客户"
    )
    from_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_account.account_id"), nullable=True, index=True, comment="付款账户"
    )
    from_card_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_card.card_id"), nullable=True, index=True, comment="付款卡"
    )
    beneficiary_account_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="收款账户哈希"
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, comment="交易金额")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY", comment="币种")
    txn_type: Mapped[TransactionType] = mapped_column(
        enum_type(TransactionType, "transaction_type_enum"), nullable=False, comment="交易类型"
    )
    channel: Mapped[TransactionChannel] = mapped_column(
        enum_type(TransactionChannel, "transaction_channel_enum"), nullable=False, comment="交易渠道"
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="设备标识")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="演示IP")
    geo: Mapped[str] = mapped_column(String(100), nullable=False, comment="交易城市或地理编码")
    txn_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="交易时间")
    status: Mapped[TransactionStatus] = mapped_column(
        enum_type(TransactionStatus, "transaction_status_enum"),
        nullable=False,
        default=TransactionStatus.PENDING,
        comment="交易状态",
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("idx_bank_txn_user_time", "user_id", "txn_time"),
        Index("idx_bank_txn_beneficiary_time", "beneficiary_account_hash", "txn_time"),
    )


class LoanApplication(Base):
    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款申请ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_info.user_id"), nullable=False, index=True, comment="申请人"
    )
    institution_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="模拟申请机构")
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, comment="申请金额")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    purpose: Mapped[str] = mapped_column(String(100), nullable=False, comment="贷款用途")
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="申报月收入")
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, comment="负债收入比")
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="申请设备")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="申请IP")
    apply_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="申请时间")
    status: Mapped[LoanStatus] = mapped_column(
        enum_type(LoanStatus, "loan_status_enum"),
        nullable=False,
        default=LoanStatus.SUBMITTED,
        comment="申请状态",
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("term_months BETWEEN 1 AND 360", name="term_months_range"),
        CheckConstraint("monthly_income >= 0", name="monthly_income_non_negative"),
        CheckConstraint("debt_ratio BETWEEN 0 AND 1", name="debt_ratio_range"),
        Index("idx_loan_user_apply_at", "user_id", "apply_at"),
        Index("idx_loan_institution_apply_at", "institution_code", "apply_at"),
    )


class LoginLog(Base):
    __tablename__ = "login_log"

    login_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="登录事件ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_info.user_id"), nullable=False, index=True, comment="登录用户"
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="登录设备")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="登录IP")
    geo: Mapped[str] = mapped_column(String(100), nullable=False, comment="登录城市")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否成功")
    fail_reason: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="失败原因")
    login_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="登录时间")

    __table_args__ = (Index("idx_login_user_time", "user_id", "login_at"),)


class DeviceFingerprint(Base):
    __tablename__ = "device_fingerprint"

    binding_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="绑定记录ID",
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="设备ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_info.user_id"), nullable=False, index=True, comment="关联用户"
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备指纹哈希")
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现")
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近出现")
    os: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作系统")
    browser: Mapped[str] = mapped_column(String(50), nullable=False, comment="浏览器或客户端")
    is_rooted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否Root或越狱")
    is_emulator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否模拟器")

    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="uq_device_user"),
        Index("idx_device_last_seen", "last_seen"),
    )


class IpGeoLocation(Base):
    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True, comment="演示IP")
    country: Mapped[str] = mapped_column(String(50), nullable=False, comment="国家")
    province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省份")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="城市")
    isp: Mapped[str] = mapped_column(String(100), nullable=False, comment="运营商")
    is_proxy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否代理")
    is_tor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否Tor出口")
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="IP风险分")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    __table_args__ = (CheckConstraint("risk_score BETWEEN 0 AND 100", name="risk_score_range"),)


BUSINESS_TABLE_NAMES = (
    "customer_info",
    "bank_account",
    "bank_card",
    "bank_transaction",
    "loan_application",
    "login_log",
    "device_fingerprint",
    "ip_geo_location",
)
