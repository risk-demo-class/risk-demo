"""
银行风控系统 - ORM 模型定义
==========================
12 张表, 覆盖登录/转账/贷款/信用卡四大场景.
SQLAlchemy 2.0 声明式映射, 所有字段与 init_bank_risk_tables.sql 一致.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, SmallInteger, String, Text, DECIMAL,
    DateTime, JSON, ForeignKey, Index, CHAR,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import TypeDecorator


class TINYINT(TypeDecorator):
    """MySQL TINYINT 兼容类型 (SQLAlchemy 2.0+ 中 TINYINT 已被移除)."""
    impl = SmallInteger
    cache_ok = True


class Base(DeclarativeBase):
    pass


# ============================================================
# 第一层: 基础维度表
# ============================================================

class DeviceFingerprint(Base):
    """设备指纹表"""
    __tablename__ = "device_fingerprint"

    device_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="设备 ID")
    fingerprint_hash = Column(CHAR(64), nullable=False, unique=True, comment="设备指纹哈希 (SHA-256)")
    os = Column(String(32), nullable=True, comment="操作系统")
    browser = Column(String(32), nullable=True, comment="浏览器")
    is_emulator = Column(TINYINT, default=0, comment="是否模拟器")
    is_root = Column(TINYINT, default=0, comment="是否越狱/root")
    status = Column(TINYINT, nullable=False, default=1, comment="设备状态: 1=正常, 2=高风险, 3=黑名单")
    first_seen = Column(DateTime, nullable=False, comment="首次出现时间")
    last_seen = Column(DateTime, nullable=False, comment="最近出现时间")


class IpGeoLocation(Base):
    """IP 地理位置表"""
    __tablename__ = "ip_geo_location"

    ip = Column(String(45), primary_key=True, comment="IP 地址")
    country = Column(String(64), nullable=True, comment="国家")
    province = Column(String(64), nullable=True, comment="省份")
    city = Column(String(64), nullable=True, comment="城市")
    isp = Column(String(32), nullable=True, comment="运营商")
    is_proxy = Column(TINYINT, nullable=False, default=0, comment="是否代理")
    is_tor = Column(TINYINT, nullable=False, default=0, comment="是否 Tor")
    is_vpn = Column(TINYINT, nullable=False, default=0, comment="是否 VPN")
    is_mobile = Column(TINYINT, nullable=False, default=0, comment="是否移动网络")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, comment="更新时间")


class BlacklistExtra(Base):
    """黑名单扩展表"""
    __tablename__ = "blacklist_extra"

    entry_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="名单 ID")
    type = Column(TINYINT, nullable=False, comment="名单类型: 1=设备, 2=IP, 3=银行卡号, 4=身份证, 5=手机号")
    value = Column(String(128), nullable=False, comment="命中值")
    reason = Column(String(256), nullable=True, comment="入单原因")
    source = Column(String(32), nullable=False, default="内部", comment="来源")
    risk_level = Column(TINYINT, nullable=False, default=3, comment="名单风险等级: 1-4")
    expire_at = Column(DateTime, nullable=True, comment="过期时间")
    status = Column(TINYINT, nullable=False, default=1, comment="状态: 1=有效, 0=失效")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class RuleConfig(Base):
    """规则配置表"""
    __tablename__ = "rule_config"

    rule_id = Column(String(16), primary_key=True, comment="规则编号")
    rule_name = Column(String(64), nullable=False, comment="规则名称")
    scene = Column(String(16), nullable=False, comment="所属场景")
    conditions = Column(JSON, nullable=False, comment="条件表达式 (含窗口/阈值)")
    risk_level = Column(TINYINT, nullable=False, comment="风险等级: 1=低, 2=中, 3=高, 4=极高")
    decision = Column(String(16), nullable=False, comment="决策: PASS/CHALLENGE/MANUAL/REJECT")
    action = Column(String(64), nullable=True, comment="处置动作")
    priority = Column(Integer, nullable=False, default=100, comment="优先级")
    status = Column(TINYINT, nullable=False, default=1, comment="状态: 1=启用, 0=停用")
    operator = Column(String(32), default="admin")
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


# ============================================================
# 第二层: 用户相关表
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="用户 ID")
    name = Column(String(64), nullable=False, comment="姓名")
    id_card_hash = Column(CHAR(64), nullable=False, unique=True, comment="身份证号哈希")
    phone_hash = Column(CHAR(64), nullable=False, unique=True, comment="手机号哈希")
    credit_score = Column(Integer, nullable=True, comment="信用分 (300-850)")
    kyc_level = Column(TINYINT, nullable=False, default=1, comment="KYC 等级: 1-4")
    risk_tag = Column(String(128), nullable=True, comment="风险标签")
    status = Column(TINYINT, nullable=False, default=1, comment="状态: 1=正常, 2=冻结, 3=止付, 4=销户")
    register_at = Column(DateTime, nullable=False, comment="注册时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now)

    # 关系
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    cards = relationship("BankCard", back_populates="user")


class UserProfile(Base):
    """用户画像表"""
    __tablename__ = "user_profile"

    user_id = Column(BigInteger, ForeignKey("user_info.user_id"), primary_key=True, comment="用户 ID")
    common_city = Column(String(64), nullable=True, comment="常用城市")
    common_device_id = Column(BigInteger, nullable=True, comment="常用设备 ID")
    avg_txn_amount = Column(DECIMAL(18, 2), nullable=True, comment="平均单笔交易金额")
    txn_freq_day = Column(DECIMAL(8, 2), nullable=True, comment="日均交易笔数")
    active_hours = Column(String(32), nullable=True, comment="常用活跃时段")
    profile_at = Column(DateTime, nullable=False, default=datetime.now, comment="画像更新时间")

    user = relationship("UserInfo", back_populates="profile")


class BankCard(Base):
    """银行卡表"""
    __tablename__ = "bank_card"

    card_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="卡 ID")
    user_id = Column(BigInteger, ForeignKey("user_info.user_id"), nullable=False, comment="持卡人")
    card_no_hash = Column(CHAR(64), nullable=False, unique=True, comment="卡号哈希")
    bank_code = Column(String(16), nullable=False, comment="发卡行代码")
    card_type = Column(TINYINT, nullable=False, comment="卡类型: 1=储蓄卡, 2=信用卡")
    credit_limit = Column(DECIMAL(18, 2), nullable=True, comment="信用卡额度")
    single_limit = Column(DECIMAL(18, 2), nullable=False, default=50000.00, comment="单笔限额")
    daily_limit = Column(DECIMAL(18, 2), nullable=False, default=200000.00, comment="单日限额")
    status = Column(TINYINT, nullable=False, default=1, comment="状态: 1=正常, 2=冻结, 3=止付, 4=挂失, 5=销户")
    open_at = Column(DateTime, nullable=False, comment="开户时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now)

    user = relationship("UserInfo", back_populates="cards")


# ============================================================
# 第三层: 业务事件表
# ============================================================

class LoginLog(Base):
    """登录日志表"""
    __tablename__ = "login_log"

    login_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="登录 ID")
    user_id = Column(BigInteger, nullable=False, comment="用户 ID")
    device_id = Column(BigInteger, nullable=True, comment="设备 ID")
    ip = Column(String(45), nullable=False, comment="登录 IP")
    geo = Column(String(64), nullable=True, comment="省市")
    success = Column(TINYINT, nullable=False, comment="是否成功: 1=成功, 0=失败")
    fail_reason = Column(String(128), nullable=True, comment="失败原因")
    login_at = Column(DateTime, nullable=False, comment="登录时间")

    __table_args__ = (
        Index("idx_login_user_time", "user_id", "login_at"),
        Index("idx_login_device_time", "device_id", "login_at"),
        Index("idx_login_ip_time", "ip", "login_at"),
    )


class Transaction(Base):
    """交易表"""
    __tablename__ = "transaction"

    txn_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="交易 ID")
    from_card_id = Column(BigInteger, nullable=False, comment="出款卡 ID")
    to_card_id = Column(BigInteger, nullable=True, comment="入款卡 ID")
    to_card_no_hash = Column(CHAR(64), nullable=True, comment="对手方卡号哈希")
    to_account_name_hash = Column(CHAR(64), nullable=True, comment="对手方户名哈希")
    to_bank_code = Column(String(16), nullable=True, comment="对手方银行代码")
    amount = Column(DECIMAL(18, 2), nullable=False, comment="交易金额")
    txn_type = Column(TINYINT, nullable=False, comment="交易类型: 1=转账, 2=支付, 3=取现, 4=还款, 5=收款")
    channel = Column(String(16), nullable=False, default="APP", comment="渠道")
    device_id = Column(BigInteger, nullable=True, comment="设备 ID")
    ip = Column(String(45), nullable=True, comment="交易 IP")
    geo = Column(String(64), nullable=True, comment="省市")
    risk_score = Column(DECIMAL(5, 2), nullable=True, comment="风控评分 (0-100)")
    status = Column(TINYINT, nullable=False, default=1, comment="状态: 1=成功, 2=失败, 3=挂起, 4=拒绝")
    created_at = Column(DateTime, nullable=False, comment="交易时间")

    __table_args__ = (
        Index("idx_txn_from_card_time", "from_card_id", "created_at"),
        Index("idx_txn_to_card_time", "to_card_id", "created_at"),
        Index("idx_txn_device_time", "device_id", "created_at"),
    )


class LoanApplication(Base):
    """贷款申请表"""
    __tablename__ = "loan_application"

    loan_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="申请 ID")
    user_id = Column(BigInteger, ForeignKey("user_info.user_id"), nullable=False, comment="申请人")
    amount = Column(DECIMAL(18, 2), nullable=False, comment="申请金额")
    term_months = Column(Integer, nullable=False, comment="期限（月）")
    purpose = Column(String(32), nullable=False, comment="用途")
    monthly_income = Column(DECIMAL(18, 2), nullable=False, comment="月收入")
    debt_ratio = Column(DECIMAL(5, 2), nullable=False, comment="负债率")
    credit_query_1m = Column(Integer, default=0, comment="近 1 月征信查询次数")
    credit_query_3m = Column(Integer, default=0, comment="近 3 月征信查询次数")
    credit_query_6m = Column(Integer, default=0, comment="近 6 月征信查询次数")
    channel = Column(String(16), nullable=False, default="APP", comment="申请渠道")
    device_id = Column(BigInteger, nullable=True, comment="申请设备 ID")
    ip = Column(String(45), nullable=True, comment="申请 IP")
    geo = Column(String(64), nullable=True, comment="省市")
    status = Column(TINYINT, nullable=False, default=1, comment="状态: 1=待审批, 2=通过, 3=拒绝, 4=人工, 5=已放款, 6=已结清, 7=逾期")
    applied_at = Column(DateTime, nullable=False, comment="申请时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class RiskEvent(Base):
    """风险事件表"""
    __tablename__ = "risk_event"

    event_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="事件 ID")
    event_type = Column(String(32), nullable=False, comment="事件类型")
    user_id = Column(BigInteger, nullable=True, comment="用户 ID")
    card_id = Column(BigInteger, nullable=True, comment="卡 ID")
    device_id = Column(BigInteger, nullable=True, comment="设备 ID")
    ip = Column(String(45), nullable=True, comment="IP 地址")
    amount = Column(DECIMAL(18, 2), nullable=True, comment="金额")
    rule_ids = Column(String(128), nullable=True, comment="命中规则编号列表")
    risk_score = Column(DECIMAL(5, 2), nullable=True, comment="模型评分 (0-100)")
    decision = Column(String(16), nullable=False, comment="决策结果")
    action = Column(String(64), nullable=True, comment="处置动作")
    status = Column(TINYINT, nullable=False, default=1, comment="处理状态: 1=待处理, 2=已处理, 3=误报")
    handler = Column(String(32), nullable=True, comment="处理人")
    handled_at = Column(DateTime, nullable=True, comment="处理时间")
    remark = Column(String(256), nullable=True, comment="处理备注")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="事件时间")

    __table_args__ = (
        Index("idx_risk_event_user", "user_id"),
        Index("idx_risk_event_type", "event_type"),
        Index("idx_risk_event_decision", "decision"),
        Index("idx_risk_event_status", "status"),
    )


class DeviceUserRel(Base):
    """设备用户关联表 (多对多)"""
    __tablename__ = "device_user_rel"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, ForeignKey("device_fingerprint.device_id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("user_info.user_id"), nullable=False)
    rel_type = Column(TINYINT, nullable=False, default=1, comment="关联类型: 1=登录, 2=交易, 3=申请")
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("uk_device_user", "device_id", "user_id", unique=True),
    )
