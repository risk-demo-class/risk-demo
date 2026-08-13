"""银行风控教学系统的 8 张业务表 ORM。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    """虚构银行客户。"""

    __tablename__ = "user_info"
    __table_args__ = (
        UniqueConstraint("id_card_hash", name="uq_user_id_card_hash"),
        Index("ix_user_credit_score", "credit_score"),
        Index("ix_user_register_at", "register_at"),
        Index("ix_user_kyc_credit", "kyc_level", "credit_score"),
    )

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="虚构用户标识名"
    )
    id_card_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="虚构身份证号摘要"
    )
    credit_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("600"), comment="教学信用分"
    )
    register_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="注册时间"
    )
    kyc_level: Mapped[str] = mapped_column(
        Enum("基础", "标准", "增强", name="kyc_level_enum"),
        nullable=False,
        server_default=text("'基础'"),
        comment="KYC等级",
    )


class BankCard(Base):
    """客户银行卡；同一客户可以持有多张卡。"""

    __tablename__ = "bank_card"
    __table_args__ = (
        UniqueConstraint("card_no_hash", name="uq_bank_card_no_hash"),
        Index("ix_bank_card_user_active", "user_id", "is_active"),
        Index("ix_bank_card_bank_type", "bank_code", "card_type"),
        CheckConstraint("credit_limit >= 0", name="ck_bank_card_credit_limit"),
    )

    card_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="银行卡ID"
    )
    user_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("user_info.user_id"),
        nullable=False,
        comment="所属用户ID",
    )
    card_no_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="虚构卡号摘要"
    )
    bank_code: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="虚构机构代码"
    )
    card_type: Mapped[str] = mapped_column(
        Enum("借记卡", "信用卡", name="bank_card_type_enum"),
        nullable=False,
        comment="卡类型",
    )
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        server_default=text("0.00"),
        comment="教学信用额度",
    )
    bind_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="绑卡时间"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1"), comment="卡关系是否有效"
    )


class IpGeoLocation(Base):
    """虚构 IP 标识对应的地理与网络环境。"""

    __tablename__ = "ip_geo_location"
    __table_args__ = (
        Index("ix_ip_geo", "country", "province", "city"),
        Index("ix_ip_proxy_tor", "is_proxy", "is_tor"),
    )

    ip: Mapped[str] = mapped_column(String(64), primary_key=True, comment="虚构IP标识")
    country: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="国家/地区"
    )
    province: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="省级区域"
    )
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="城市")
    isp: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="虚构网络服务商"
    )
    is_proxy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="是否代理"
    )
    is_tor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="是否Tor出口"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="环境更新时间"
    )


class DeviceFingerprint(Base):
    """设备与用户的逻辑关联；复合主键支持同一设备关联多个用户。"""

    __tablename__ = "device_fingerprint"
    __table_args__ = (
        Index("ix_device_fingerprint_hash", "fingerprint_hash"),
        Index("ix_device_user_last_seen", "user_id", "last_seen"),
        CheckConstraint("last_seen >= first_seen", name="ck_device_seen_order"),
    )

    device_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="设备ID"
    )
    user_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("user_info.user_id"),
        primary_key=True,
        comment="关联用户ID",
    )
    fingerprint_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="设备指纹摘要"
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="首次出现时间"
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="最近出现时间"
    )
    os: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="操作系统枚举值"
    )
    browser: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="浏览器枚举值"
    )


class Transaction(Base):
    """银行转账或支付交易。"""

    __tablename__ = "bank_transaction"
    __table_args__ = (
        Index("ix_bank_transaction_from_time", "from_card", "txn_at"),
        Index("ix_bank_transaction_to_time", "to_card", "txn_at"),
        Index("ix_bank_transaction_device_time", "device_id", "txn_at"),
        Index("ix_bank_transaction_ip_time", "ip", "txn_at"),
        Index("ix_bank_transaction_time_amount", "txn_at", "amount"),
        CheckConstraint("amount > 0", name="ck_bank_transaction_amount"),
        CheckConstraint(
            "from_card <> to_card", name="ck_bank_transaction_distinct_cards"
        ),
    )

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    from_card: Mapped[str] = mapped_column(
        String(50), ForeignKey("bank_card.card_id"), nullable=False, comment="付款卡ID"
    )
    to_card: Mapped[str] = mapped_column(
        String(50), ForeignKey("bank_card.card_id"), nullable=False, comment="收款卡ID"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, comment="交易金额"
    )
    channel: Mapped[str] = mapped_column(
        Enum(
            "手机银行",
            "网上银行",
            "柜面",
            "ATM",
            "快捷支付",
            name="transaction_channel_enum",
        ),
        nullable=False,
        comment="交易渠道",
    )
    device_id: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="逻辑关联设备ID"
    )
    ip: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ip_geo_location.ip"),
        nullable=False,
        comment="虚构IP标识",
    )
    geo: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="事件地理编码"
    )
    txn_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="交易时间"
    )
    status: Mapped[str] = mapped_column(
        Enum("成功", "失败", "处理中", name="transaction_status_enum"),
        nullable=False,
        server_default=text("'成功'"),
        comment="交易状态",
    )


class LoanApplication(Base):
    """贷款申请，保留机构和时间以支持多头借贷查询。"""

    __tablename__ = "loan_application"
    __table_args__ = (
        Index("ix_loan_user_apply", "user_id", "apply_at"),
        Index("ix_loan_institution_apply", "institution_code", "apply_at"),
        Index("ix_loan_apply_amount", "apply_at", "amount"),
        CheckConstraint("amount > 0", name="ck_loan_amount"),
        CheckConstraint("term_months > 0", name="ck_loan_term"),
        CheckConstraint("monthly_income >= 0", name="ck_loan_income"),
        CheckConstraint("debt_ratio >= 0", name="ck_loan_debt_ratio"),
    )

    loan_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="贷款申请ID"
    )
    user_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("user_info.user_id"),
        nullable=False,
        comment="申请用户ID",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, comment="申请金额"
    )
    term_months: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="期限（月）"
    )
    purpose: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="贷款用途"
    )
    monthly_income: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, comment="月收入"
    )
    debt_ratio: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, comment="负债率"
    )
    institution_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="虚构申请机构代码"
    )
    apply_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="申请时间"
    )
    status: Mapped[str] = mapped_column(
        Enum("待审核", "已批准", "已拒绝", name="loan_status_enum"),
        nullable=False,
        server_default=text("'待审核'"),
        comment="申请状态",
    )


class LoginLog(Base):
    """银行账户登录记录。"""

    __tablename__ = "login_log"
    __table_args__ = (
        ForeignKeyConstraint(
            ["device_id", "user_id"],
            ["device_fingerprint.device_id", "device_fingerprint.user_id"],
            name="fk_login_device_user",
        ),
        Index("ix_login_user_time", "user_id", "login_at"),
        Index("ix_login_device_time", "device_id", "login_at"),
        Index("ix_login_ip_time", "ip", "login_at"),
    )

    login_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="登录记录ID"
    )
    user_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("user_info.user_id"),
        nullable=False,
        comment="登录用户ID",
    )
    device_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="设备ID")
    ip: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ip_geo_location.ip"),
        nullable=False,
        comment="虚构IP标识",
    )
    geo: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="登录地理编码"
    )
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="是否登录成功"
    )
    login_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="登录时间"
    )


class BlacklistExtra(Base):
    """银行外部/扩展名单数据源，不作为实时执行真相。"""

    __tablename__ = "blacklist_extra"
    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_blacklist_extra_type_value"),
        Index("ix_blacklist_extra_expire", "expire_at"),
        Index("ix_blacklist_extra_type_created", "type", "created_at"),
    )

    entry_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="扩展名单ID"
    )
    type: Mapped[str] = mapped_column(
        Enum(
            "用户",
            "设备指纹",
            "IP",
            "银行卡号",
            "身份证号",
            name="blacklist_extra_type_enum",
        ),
        nullable=False,
        comment="名单类型",
    )
    value: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="掩码或不可逆摘要"
    )
    reason: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="教学名单原因"
    )
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="到期时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
