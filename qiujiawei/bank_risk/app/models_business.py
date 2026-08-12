"""
银行风控系统 - 业务表 ORM (8 张)
只读映射银行核心业务系统的实体 (用户/银行卡/交易/贷款/登录/设备/IP/黑名单)
不参与风控决策本身, 但被特征工程和规则引擎查询

跟 AI_Risk/app/models_business.py 结构一致, 但场景换为银行:
  - 信用卡 / 贷款 / 转账 / 登录 4 大场景
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bank_risk.app.database import Base


# ============================================================
# 用户与账户
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名")
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="身份证号哈希")
    credit_score: Mapped[int] = mapped_column(Integer, default=600, comment="信用分")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="注册时间")
    kyc_level: Mapped[int] = mapped_column(Integer, default=0, comment="KYC等级(0-3)")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="手机号")
    email: Mapped[Optional[str]] = mapped_column(String(100), comment="邮箱")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="状态(active/frozen/closed)")


class BankCard(Base):
    """银行卡表"""
    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="卡ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    card_no_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="卡号哈希")
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="银行编码")
    card_type: Mapped[str] = mapped_column(String(20), default="debit", comment="卡类型(debit/credit/savings)")
    credit_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), comment="信用额度")
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), comment="余额")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="状态")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )


# ============================================================
# 交易与贷款
# ============================================================

class Transaction(Base):
    """交易记录表"""
    __tablename__ = "transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    from_card: Mapped[str] = mapped_column(String(50), nullable=False, comment="转出卡ID")
    to_card: Mapped[Optional[str]] = mapped_column(String(50), comment="转入卡ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, comment="金额")
    channel: Mapped[str] = mapped_column(String(20), default="online", comment="渠道(online/atm/counter/mobile/pos)")
    txn_type: Mapped[str] = mapped_column(String(20), default="transfer", comment="交易类型(transfer/payment/withdrawal/deposit)")
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(45), comment="IP地址")
    geo: Mapped[Optional[str]] = mapped_column(String(100), comment="地理位置")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="状态(pending/success/failed)")
    txn_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="交易时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )


class LoanApplication(Base):
    """贷款申请表"""
    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, comment="申请金额")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    purpose: Mapped[Optional[str]] = mapped_column(String(200), comment="用途")
    monthly_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), comment="月收入")
    debt_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), comment="负债率")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="状态(pending/approved/rejected/disbursed)")
    apply_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="申请时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )


# ============================================================
# 登录与设备
# ============================================================

class LoginLog(Base):
    """登录日志表"""
    __tablename__ = "login_log"

    login_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="登录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(45), comment="IP地址")
    geo: Mapped[Optional[str]] = mapped_column(String(100), comment="地理位置")
    success: Mapped[int] = mapped_column(Integer, default=1, comment="是否成功(1/0)")
    fail_reason: Mapped[Optional[str]] = mapped_column(String(100), comment="失败原因")
    login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="登录时间")


class DeviceFingerprint(Base):
    """设备指纹表"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="设备ID")
    user_id: Mapped[Optional[str]] = mapped_column(String(50), comment="用户ID")
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="指纹哈希")
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="首次出现时间")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近出现时间")
    os: Mapped[Optional[str]] = mapped_column(String(50), comment="操作系统")
    browser: Mapped[Optional[str]] = mapped_column(String(50), comment="浏览器")
    risk_score: Mapped[int] = mapped_column(Integer, default=0, comment="风险评分(0-100)")


# ============================================================
# IP 库与扩展黑名单
# ============================================================

class IpGeoLocation(Base):
    """IP 地理位置库表"""
    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(45), primary_key=True, comment="IP地址")
    country: Mapped[Optional[str]] = mapped_column(String(50), comment="国家")
    province: Mapped[Optional[str]] = mapped_column(String(50), comment="省")
    city: Mapped[Optional[str]] = mapped_column(String(50), comment="市")
    isp: Mapped[Optional[str]] = mapped_column(String(100), comment="ISP")
    is_proxy: Mapped[int] = mapped_column(Integer, default=0, comment="是否代理(1/0)")
    is_tor: Mapped[int] = mapped_column(Integer, default=0, comment="是否Tor(1/0)")
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="更新时间",
    )


class BlacklistExtra(Base):
    """扩展黑名单表"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    type: Mapped[str] = mapped_column(String(20), nullable=False, comment="类型(user/device/ip/card/id_card)")
    value: Mapped[str] = mapped_column(String(100), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(200), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )
