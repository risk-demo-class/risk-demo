"""
银行风控系统 - 业务表 ORM (8 张)
只读映射银行业务系统的核心实体 (用户/银行卡/交易/贷款/登录/设备/IP/黑名单扩展)
不参与风控决策本身, 但被特征工程和规则引擎查询

与电商版差异: 全新表, 覆盖信用卡/贷款/转账/登录 4 大场景
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与账户基础
# ============================================================

class UserInfo(Base):
    """银行用户信息表 (较电商版: 加 KYC 等级 / 信用分)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[Optional[str]] = mapped_column(String(50), comment="姓名")
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="身份证号哈希(脱敏)")
    credit_score: Mapped[Optional[int]] = mapped_column(Integer, comment="人行信用分(300-850)")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="注册时间")
    kyc_level: Mapped[Optional[int]] = mapped_column(
        Integer, default=1, comment="KYC 等级 (1=L1 实名 / 2=L2 人脸 / 3=L3 面签 / 4=L4 高级)",
    )


class BankCard(Base):
    """银行卡表 (全新表, 每用户 N 张卡)"""
    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="卡ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    card_no_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="卡号哈希(脱敏)")
    bank_code: Mapped[Optional[str]] = mapped_column(String(20), comment="发卡行代码")
    card_type: Mapped[Optional[str]] = mapped_column(
        Enum("借记卡", "信用卡", name="bank_card_type_enum"),
        comment="卡类型",
    )
    credit_limit: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), default=0, comment="授信额度(信用卡), 借记卡为 0",
    )


# ============================================================
# 交易域
# ============================================================

class Transaction(Base):
    """交易表 (全新表, 转账/支付都用这张)"""
    __tablename__ = "transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    from_card: Mapped[str] = mapped_column(String(50), nullable=False, comment="付款卡ID")
    to_card: Mapped[Optional[str]] = mapped_column(String(50), comment="收款卡ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="交易金额")
    channel: Mapped[Optional[str]] = mapped_column(
        Enum("APP", "网银", "ATM", "第三方", name="txn_channel_enum"),
        comment="交易渠道",
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="设备指纹ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="IP 地址")
    geo: Mapped[Optional[str]] = mapped_column(String(100), comment="地理位置(省-市)")
    txn_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="交易时间")


class LoanApplication(Base):
    """贷款申请表 (全新表)"""
    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="申请金额")
    term_months: Mapped[Optional[int]] = mapped_column(Integer, comment="期限(月)")
    purpose: Mapped[Optional[str]] = mapped_column(String(100), comment="贷款用途")
    monthly_income: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), comment="月收入",
    )
    debt_ratio: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4), comment="负债率(月还款/月收入)",
    )
    apply_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="申请时间")


class LoginLog(Base):
    """登录日志表 (全新表, 电商版没专门做)"""
    __tablename__ = "login_log"

    login_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="登录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="设备指纹ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="IP 地址")
    geo: Mapped[Optional[str]] = mapped_column(String(100), comment="地理位置(省-市)")
    success: Mapped[Optional[int]] = mapped_column(Integer, default=1, comment="是否登录成功(1/0)")
    login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="登录时间")


# ============================================================
# 设备 / 网络域 (银行业专属)
# ============================================================

class DeviceFingerprint(Base):
    """设备指纹表 (全新表, 银行业专属)"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="设备指纹ID")
    user_id: Mapped[Optional[str]] = mapped_column(String(50), comment="归属用户(可能多人共用)")
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="指纹哈希")
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="首次出现时间")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近出现时间")
    os: Mapped[Optional[str]] = mapped_column(String(50), comment="操作系统")
    browser: Mapped[Optional[str]] = mapped_column(String(50), comment="浏览器")


class IpGeoLocation(Base):
    """IP 地理位置表 (全新表)"""
    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(50), primary_key=True, comment="IP 地址")
    country: Mapped[Optional[str]] = mapped_column(String(50), comment="国家")
    province: Mapped[Optional[str]] = mapped_column(String(50), comment="省")
    city: Mapped[Optional[str]] = mapped_column(String(50), comment="市")
    isp: Mapped[Optional[str]] = mapped_column(String(50), comment="运营商")
    is_proxy: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="是否代理IP(1/0)")
    is_tor: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="是否Tor出口(1/0)")


# ============================================================
# 黑名单扩展 (银行业专属类型)
# ============================================================

class BlacklistExtra(Base):
    """黑名单扩展表 (type 加 设备指纹/IP/银行卡号/身份证号)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    type: Mapped[str] = mapped_column(
        Enum("设备指纹", "IP", "银行卡号", "身份证号", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
