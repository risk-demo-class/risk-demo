"""
银行风控系统 - 业务表 ORM (8 张)
完全替换原电商版 17 张业务表.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与基础信息
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名")
    id_card_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="身份证号SHA256")
    credit_score: Mapped[int] = mapped_column(Integer, default=600, comment="征信分(350-950)")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    kyc_level: Mapped[str] = mapped_column(
        Enum("未认证", "L1", "L2", "L3", name="kyc_level_enum"),
        default="未认证", comment="KYC认证等级",
    )


class DeviceFingerprint(Base):
    """设备指纹表"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="用户ID")
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备指纹Hash")
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次发现时间")
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最后活跃时间")
    os: Mapped[Optional[str]] = mapped_column(String(50), comment="操作系统")
    browser: Mapped[Optional[str]] = mapped_column(String(50), comment="浏览器")

    __table_args__ = (
        Index("idx_df_user_id", "user_id"),
    )


class IpGeoLocation(Base):
    """IP地理信息表"""
    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(50), primary_key=True, comment="IP地址")
    country: Mapped[Optional[str]] = mapped_column(String(50), comment="国家")
    province: Mapped[Optional[str]] = mapped_column(String(50), comment="省份")
    city: Mapped[Optional[str]] = mapped_column(String(50), comment="城市")
    isp: Mapped[Optional[str]] = mapped_column(String(50), comment="运营商")
    is_proxy: Mapped[int] = mapped_column(Integer, default=0, comment="是否代理IP(0=否,1=是)")
    is_tor: Mapped[int] = mapped_column(Integer, default=0, comment="是否Tor出口(0=否,1=是)")


class BlacklistExtra(Base):
    """业务黑名单扩展表 (银行版)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    type: Mapped[str] = mapped_column(
        Enum("设备指纹", "IP", "银行卡号", "身份证号", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")


# ============================================================
# 账户与卡片
# ============================================================

class BankCard(Base):
    """银行卡表"""
    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="卡ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="用户ID")
    card_no_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="卡号SHA256")
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="银行代码")
    card_type: Mapped[str] = mapped_column(
        Enum("借记卡", "信用卡", name="card_type_enum"),
        nullable=False, comment="卡类型",
    )
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="信用额度(信用卡)")

    __table_args__ = (
        Index("idx_bc_user_id", "user_id"),
    )


# ============================================================
# 交易与贷款
# ============================================================

class Transaction(Base):
    """交易记录表 (转账/支付)"""
    __tablename__ = "transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    from_card: Mapped[str] = mapped_column(String(50), ForeignKey("bank_card.card_id"), nullable=False, comment="发出卡ID")
    to_card: Mapped[str] = mapped_column(String(50), nullable=False, comment="接收卡ID(可为外行)")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="交易金额")
    channel: Mapped[str] = mapped_column(
        Enum("网银", "手机银行", "ATM", "柜台", name="txn_channel_enum"),
        nullable=False, comment="交易渠道",
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="交易IP")
    geo: Mapped[Optional[str]] = mapped_column(String(100), comment="交易地理位置")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="交易时间")

    __table_args__ = (
        Index("idx_txn_from_card", "from_card"),
        Index("idx_txn_create_time", "create_time"),
    )


class LoanApplication(Base):
    """贷款申请表"""
    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款申请ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="用户ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="申请金额")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    purpose: Mapped[str] = mapped_column(String(200), nullable=False, comment="贷款用途")
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="月收入")
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, comment="负债率(%)")
    status: Mapped[str] = mapped_column(
        Enum("待审核", "通过", "拒绝", name="loan_status_enum"),
        default="待审核", comment="审核状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")

    __table_args__ = (
        Index("idx_la_user_id", "user_id"),
    )


class LoginLog(Base):
    """登录日志表"""
    __tablename__ = "login_log"

    login_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="登录ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="用户ID")
    device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="登录IP")
    geo: Mapped[Optional[str]] = mapped_column(String(100), comment="登录地理位置")
    success: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否成功(1=成功,0=失败)")
    login_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="登录时间")

    __table_args__ = (
        Index("idx_ll_user_id", "user_id"),
        Index("idx_ll_login_at", "login_at"),
    )