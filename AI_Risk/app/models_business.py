"""
银行工商风控系统 - 业务表 ORM (30 张)
覆盖 6 大领域: 用户KYC / 银行卡 / 交易 / 贷款 / 登录设备 / 风控辅助数据
只读映射现有业务系统的核心实体, 不参与风控决策本身, 但被特征工程和规则引擎查询
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 第一域: 用户与 KYC (5 张)
# ============================================================

class UserInfo(Base):
    """用户信息表 — 银行核心客户主表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="姓名 SHA256 哈希")
    id_card_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="身份证号 SHA256 哈希")
    phone_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="手机号 SHA256 哈希")
    email: Mapped[Optional[str]] = mapped_column(String(100), comment="邮箱")
    kyc_level: Mapped[str] = mapped_column(
        Enum("L1", "L2", "L3", "L4", "L5", name="kyc_level_enum"),
        default="L1", nullable=False, comment="KYC 等级 (L1-L5)",
    )
    credit_score: Mapped[int] = mapped_column(Integer, default=600, comment="行内信用评分 (300-900)")
    reg_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册日期")
    status: Mapped[str] = mapped_column(
        Enum("正常", "冻结", "销户", name="user_status_enum"),
        default="正常", nullable=False, comment="账户状态",
    )
    reg_ip: Mapped[Optional[str]] = mapped_column(String(50), comment="注册 IP")
    reg_city: Mapped[Optional[str]] = mapped_column(String(30), comment="注册城市")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_user_id_card_hash", "id_card_hash"),
        Index("idx_user_phone_hash", "phone_hash"),
        Index("idx_user_kyc_level", "kyc_level"),
        Index("idx_user_credit_score", "credit_score"),
        Index("idx_user_reg_city", "reg_city"),
    )


class UserKycRecord(Base):
    """用户 KYC 审核记录表"""
    __tablename__ = "user_kyc_record"

    kyc_record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="KYC 记录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    level_before: Mapped[str] = mapped_column(
        Enum("L1", "L2", "L3", "L4", "L5", name="kyc_level_before_enum"),
        nullable=False, comment="变更前 KYC 等级",
    )
    level_after: Mapped[str] = mapped_column(
        Enum("L1", "L2", "L3", "L4", "L5", name="kyc_level_after_enum"),
        nullable=False, comment="变更后 KYC 等级",
    )
    audit_status: Mapped[str] = mapped_column(
        Enum("待审核", "通过", "驳回", name="kyc_audit_status_enum"),
        default="待审核", comment="审核状态",
    )
    auditor: Mapped[Optional[str]] = mapped_column(String(50), comment="审核人")
    audit_remark: Mapped[Optional[str]] = mapped_column(Text, comment="审核备注")
    audit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审核时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_kyc_user_id", "user_id"),
        Index("idx_kyc_audit_time", "audit_time"),
    )


class UserEmployment(Base):
    """用户职业与收入信息表"""
    __tablename__ = "user_employment"

    employment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="职业信息ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="公司名称")
    position: Mapped[Optional[str]] = mapped_column(String(100), comment="职位")
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="月收入")
    annual_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="年收入")
    employment_status: Mapped[str] = mapped_column(
        Enum("在职", "离职", "退休", "自由职业", name="employment_status_enum"),
        default="在职", comment="就业状态",
    )
    verify_status: Mapped[str] = mapped_column(
        Enum("未验证", "验证中", "已验证", "验证失败", name="employment_verify_enum"),
        default="未验证", comment="收入验证状态",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_employment_user_id", "user_id"),
        Index("idx_employment_income", "monthly_income"),
    )


class UserContact(Base):
    """用户联系人信息表"""
    __tablename__ = "user_contact"

    contact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="联系人ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    contact_name_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="联系人姓名 SHA256 哈希")
    contact_phone_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="联系人手机号 SHA256 哈希")
    relationship: Mapped[str] = mapped_column(
        Enum("配偶", "父母", "子女", "兄弟姐妹", "朋友", "同事", name="contact_relation_enum"),
        nullable=False, comment="与用户关系",
    )
    is_emergency: Mapped[int] = mapped_column(Integer, default=0, comment="是否紧急联系人")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_contact_user_id", "user_id"),
        Index("idx_contact_phone_hash", "contact_phone_hash"),
    )


class UserEnterprise(Base):
    """企业对公信息表"""
    __tablename__ = "user_enterprise"

    enterprise_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="企业信息ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    enterprise_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="企业名称")
    credit_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="统一社会信用代码")
    legal_person_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="法定代表人身份证 SHA256")
    registered_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="注册资本 (万元)")
    business_scope: Mapped[Optional[str]] = mapped_column(Text, comment="经营范围")
    establish_date: Mapped[Optional[Date]] = mapped_column(Date, comment="成立日期")
    industry_category: Mapped[Optional[str]] = mapped_column(String(50), comment="行业分类")
    ubo_count: Mapped[int] = mapped_column(Integer, default=0, comment="受益所有人数量")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_ent_user_id", "user_id"),
        Index("idx_ent_credit_code", "credit_code"),
        Index("idx_ent_legal_person", "legal_person_hash"),
    Index("idx_ent_name", "enterprise_name"),
    )


# ============================================================
# 第二域: 银行卡 (4 张)
# ============================================================

class BankCard(Base):
    """银行卡信息表"""
    __tablename__ = "bank_card"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="卡ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    card_number_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="卡号 SHA256 哈希")
    card_type: Mapped[str] = mapped_column(
        Enum("借记卡", "信用卡", "II类户", name="card_type_enum"),
        nullable=False, comment="卡类型",
    )
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="发卡行名称")
    credit_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="授信额度")
    available_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="可用额度")
    open_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="开卡日期")
    card_status: Mapped[str] = mapped_column(
        Enum("正常", "冻结", "挂失", "注销", name="card_status_enum"),
        default="正常", nullable=False, comment="卡片状态",
    )
    is_virtual: Mapped[int] = mapped_column(Integer, default=0, comment="是否虚拟卡")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_card_user_id", "user_id"),
        Index("idx_card_number_hash", "card_number_hash"),
        Index("idx_card_type", "card_type"),
        Index("idx_card_status", "card_status"),
    )


class CardBindRecord(Base):
    """绑卡换卡记录表"""
    __tablename__ = "card_bind_record"

    bind_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="绑卡记录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    card_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="卡ID")
    bind_type: Mapped[str] = mapped_column(
        Enum("绑定", "解绑", "换卡", name="bind_type_enum"),
        nullable=False, comment="操作类型",
    )
    bind_ip: Mapped[Optional[str]] = mapped_column(String(50), comment="绑卡 IP")
    bind_device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="绑卡设备ID")
    bind_city: Mapped[Optional[str]] = mapped_column(String(30), comment="绑卡城市")
    bind_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="绑卡时间")
    unbind_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="解绑时间")

    __table_args__ = (
        Index("idx_bind_user_id", "user_id"),
        Index("idx_bind_card_id", "card_id"),
        Index("idx_bind_time", "bind_time"),
    )


class CreditCardBill(Base):
    """信用卡账单表"""
    __tablename__ = "credit_card_bill"

    bill_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="账单ID")
    card_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="卡ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    bill_month: Mapped[str] = mapped_column(String(7), nullable=False, comment="账单月份 YYYY-MM")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="账单总额")
    min_payment: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="最低还款额")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="已还金额")
    payment_status: Mapped[str] = mapped_column(
        Enum("未还", "部分还", "已还清", "逾期", name="bill_payment_status_enum"),
        default="未还", comment="还款状态",
    )
    due_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="还款截止日")
    paid_date: Mapped[Optional[Date]] = mapped_column(Date, comment="实际还款日")

    __table_args__ = (
        Index("idx_bill_card_id", "card_id"),
        Index("idx_bill_user_id", "user_id"),
        Index("idx_bill_due_date", "due_date"),
        Index("idx_bill_status", "payment_status"),
    )


class CardLimitChange(Base):
    """额度变更记录表"""
    __tablename__ = "card_limit_change"

    change_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="变更ID")
    card_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="卡ID")
    old_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="变更前额度")
    new_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="变更后额度")
    change_type: Mapped[str] = mapped_column(
        Enum("提额", "降额", "冻结", "解冻", name="limit_change_type_enum"),
        nullable=False, comment="变更类型",
    )
    change_reason: Mapped[Optional[str]] = mapped_column(Text, comment="变更原因")
    operator: Mapped[Optional[str]] = mapped_column(String(50), comment="操作人")
    change_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="变更时间")

    __table_args__ = (
        Index("idx_limit_card_id", "card_id"),
        Index("idx_limit_change_time", "change_time"),
    )


# ============================================================
# 第三域: 交易 (7 张)
# ============================================================

class Transaction(Base):
    """交易流水表"""
    __tablename__ = "transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    from_card: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="付款卡号")
    to_card: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="收款卡号")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="交易金额")
    txn_type: Mapped[str] = mapped_column(
        Enum("转账", "消费", "取现", "还款", "退款", name="txn_type_enum"),
        nullable=False, comment="交易类型",
    )
    channel: Mapped[str] = mapped_column(
        Enum("网银", "手机银行", "快捷支付", "柜面", "ATM", "POS", name="txn_channel_enum"),
        nullable=False, comment="交易渠道",
    )
    txn_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="交易时间")
    txn_status: Mapped[str] = mapped_column(
        Enum("成功", "失败", "处理中", "已冲正", name="txn_status_enum"),
        default="成功", comment="交易状态",
    )
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="交易 IP")
    city: Mapped[Optional[str]] = mapped_column(String(30), comment="交易城市")
    device_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, comment="设备指纹ID")
    remark: Mapped[Optional[str]] = mapped_column(String(500), comment="备注附言")
    is_international: Mapped[int] = mapped_column(Integer, default=0, comment="是否跨境交易")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_txn_user_id", "user_id"),
        Index("idx_txn_from_card", "from_card"),
        Index("idx_txn_to_card", "to_card"),
        Index("idx_txn_time", "txn_time"),
        Index("idx_txn_user_time", "user_id", "txn_time"),
        Index("idx_txn_to_card_time", "to_card", "txn_time"),
        Index("idx_txn_amount", "amount"),
        Index("idx_txn_device", "device_id"),
        Index("idx_txn_city", "city"),
    )


class TxnSuspiciousReport(Base):
    """大额可疑交易报告表"""
    __tablename__ = "txn_suspicious_report"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="报告ID")
    txn_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="关联交易ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    report_type: Mapped[str] = mapped_column(
        Enum("大额", "可疑", name="report_type_enum"),
        nullable=False, comment="报告类型",
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="触发金额")
    trigger_rule: Mapped[Optional[str]] = mapped_column(String(50), comment="触发规则编号")
    report_status: Mapped[str] = mapped_column(
        Enum("待上报", "已上报", "已反馈", name="report_status_enum"),
        default="待上报", comment="报告状态",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="生成时间",
    )
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="上报时间")

    __table_args__ = (
        Index("idx_report_txn_id", "txn_id"),
        Index("idx_report_user_id", "user_id"),
        Index("idx_report_type_status", "report_type", "report_status"),
        Index("idx_report_create_time", "create_time"),
    )


class TxnSplitChain(Base):
    """资金拆分链路追踪表"""
    __tablename__ = "txn_split_chain"

    chain_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="链路ID")
    root_txn_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="根交易ID")
    from_card: Mapped[str] = mapped_column(String(50), nullable=False, comment="付款卡号")
    to_card: Mapped[str] = mapped_column(String(50), nullable=False, comment="收款卡号")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="拆分金额")
    split_level: Mapped[int] = mapped_column(Integer, nullable=False, comment="拆分层级 1=第一级")
    split_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="拆分时间")

    __table_args__ = (
        Index("idx_split_root_txn", "root_txn_id"),
        Index("idx_split_to_card", "to_card"),
        Index("idx_split_time", "split_time"),
    )


class TxnAggDaily(Base):
    """用户日交易聚合表"""
    __tablename__ = "txn_agg_daily"

    agg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="聚合ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    agg_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="聚合日期")
    txn_count: Mapped[int] = mapped_column(Integer, default=0, comment="交易笔数")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="交易总额")
    avg_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="平均金额")
    max_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="最大单笔金额")
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="最小单笔金额")
    card_count: Mapped[int] = mapped_column(Integer, default=0, comment="使用卡数")
    city_count: Mapped[int] = mapped_column(Integer, default=0, comment="交易城市数")
    device_count: Mapped[int] = mapped_column(Integer, default=0, comment="使用设备数")
    counterparty_count: Mapped[int] = mapped_column(Integer, default=0, comment="对手方数量")
    night_txn_count: Mapped[int] = mapped_column(Integer, default=0, comment="深夜交易笔数 0:00-5:00")
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_agg_user_date", "user_id", "agg_date", unique=True),
        Index("idx_agg_date", "agg_date"),
    )


class TxnCounterparty(Base):
    """交易对手方信息表"""
    __tablename__ = "txn_counterparty"

    counterparty_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="对手方ID")
    counterparty_name_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="对手方名称 SHA256")
    counterparty_account_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="对手方账号 SHA256")
    counterparty_bank: Mapped[Optional[str]] = mapped_column(String(100), comment="对手方开户行")
    risk_flag: Mapped[int] = mapped_column(Integer, default=0, comment="风险标记")
    risk_region: Mapped[Optional[str]] = mapped_column(String(30), comment="对手方归属地")
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="首次出现时间")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近出现时间")
    txn_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计交易笔数")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_cpty_account", "counterparty_account_hash"),
        Index("idx_cpty_risk_flag", "risk_flag"),
    )


class TxnChannelRisk(Base):
    """渠道风险权重配置表"""
    __tablename__ = "txn_channel_risk"

    channel: Mapped[str] = mapped_column(
        Enum("网银", "手机银行", "快捷支付", "柜面", "ATM", "POS", name="channel_risk_name_enum"),
        primary_key=True, comment="交易渠道",
    )
    risk_weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, comment="风险权重")
    max_single_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="单笔限额")
    max_daily_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="日累计限额")
    max_daily_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="日笔数上限")
    is_enabled: Mapped[int] = mapped_column(Integer, default=1, comment="是否启用")


class TxnBlackAccount(Base):
    """黑产收款账户特征库"""
    __tablename__ = "txn_black_account"

    account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑账户ID")
    account_number_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="账号 SHA256")
    account_name_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="账户名 SHA256")
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), comment="开户行")
    hit_count: Mapped[int] = mapped_column(Integer, default=0, comment="命中次数")
    hit_date: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近命中时间")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", "极高", name="black_account_risk_level_enum"),
        default="中", comment="风险等级",
    )
    source: Mapped[Optional[str]] = mapped_column(String(50), comment="来源")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_blk_acct_hash", "account_number_hash"),
        Index("idx_blk_acct_level", "risk_level"),
    )


# ============================================================
# 第四域: 贷款 (5 张)
# ============================================================

class LoanApplication(Base):
    """贷款申请表"""
    __tablename__ = "loan_application"

    application_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    loan_type: Mapped[str] = mapped_column(
        Enum("个人消费贷", "个人经营贷", "住房按揭", "汽车贷款", "信用卡分期", name="loan_type_enum"),
        nullable=False, comment="贷款类型",
    )
    apply_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="申请金额")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="贷款期限月")
    purpose: Mapped[str] = mapped_column(String(200), nullable=False, comment="资金用途")
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, comment="月负债收入比")
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="申报月收入")
    credit_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="申请时信用评分")
    is_entrusted: Mapped[int] = mapped_column(Integer, default=0, comment="是否受托支付")
    apply_status: Mapped[str] = mapped_column(
        Enum("待审批", "审批中", "已通过", "已拒绝", "已放款", name="loan_apply_status_enum"),
        default="待审批", comment="申请状态",
    )
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_loan_user_id", "user_id"),
        Index("idx_loan_apply_time", "apply_time"),
        Index("idx_loan_status", "apply_status"),
    )


class LoanApproval(Base):
    """贷款审批记录表"""
    __tablename__ = "loan_approval"

    approval_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="审批ID")
    application_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    approval_status: Mapped[str] = mapped_column(
        Enum("通过", "驳回", "退回补充", name="approval_status_enum"),
        nullable=False, comment="审批结果",
    )
    approved_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="批准金额")
    approved_term: Mapped[Optional[int]] = mapped_column(Integer, comment="批准期限月")
    interest_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), comment="批准利率")
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, comment="拒绝原因")
    approver: Mapped[str] = mapped_column(String(50), nullable=False, comment="审批人")
    approval_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="审批时间")

    __table_args__ = (
        Index("idx_appr_app_id", "application_id"),
        Index("idx_appr_user_id", "user_id"),
        Index("idx_appr_time", "approval_time"),
    )


class LoanContract(Base):
    """贷款合同表"""
    __tablename__ = "loan_contract"

    contract_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="合同ID")
    application_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    loan_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="贷款金额")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限月")
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, comment="年利率")
    monthly_payment: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="月还款额")
    contract_status: Mapped[str] = mapped_column(
        Enum("正常", "关注", "次级", "可疑", "损失", "已结清", name="contract_status_enum"),
        default="正常", comment="贷款五级分类",
    )
    sign_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="签约时间")
    start_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="合同生效日")
    end_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="合同到期日")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_ctr_app_id", "application_id"),
        Index("idx_ctr_user_id", "user_id"),
        Index("idx_ctr_status", "contract_status"),
        Index("idx_ctr_dates", "start_date", "end_date"),
    )


class LoanRepayment(Base):
    """还款记录表"""
    __tablename__ = "loan_repayment"

    repayment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="还款ID")
    contract_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="合同ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    due_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="应还日期")
    due_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="应还金额")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="实还金额")
    paid_date: Mapped[Optional[Date]] = mapped_column(Date, comment="实还日期")
    payment_status: Mapped[str] = mapped_column(
        Enum("未还", "部分还", "已还清", "逾期", name="repay_payment_status_enum"),
        default="未还", comment="还款状态",
    )
    overdue_days: Mapped[int] = mapped_column(Integer, default=0, comment="逾期天数")

    __table_args__ = (
        Index("idx_repay_contract_id", "contract_id"),
        Index("idx_repay_user_id", "user_id"),
        Index("idx_repay_due_date", "due_date"),
        Index("idx_repay_status", "payment_status"),
    )


class LoanMultiPlatform(Base):
    """多头借贷记录表"""
    __tablename__ = "loan_multi_platform"

    multi_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="多头记录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    institution_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="放款机构名称")
    loan_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="贷款金额")
    loan_date: Mapped[Date] = mapped_column(Date, nullable=False, comment="放款日期")
    loan_status: Mapped[str] = mapped_column(
        Enum("正常", "已结清", "逾期", name="multi_loan_status_enum"),
        nullable=False, comment="贷款状态",
    )
    report_source: Mapped[str] = mapped_column(
        Enum("征信报告", "行内查询", "第三方", name="multi_report_source_enum"),
        nullable=False, comment="数据来源",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_multi_user_id", "user_id"),
        Index("idx_multi_loan_date", "loan_date"),
    )


# ============================================================
# 第五域: 登录与设备 (5 张)
# ============================================================

class LoginLog(Base):
    """登录日志表"""
    __tablename__ = "login_log"

    login_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="登录日志ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    login_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="登录时间")
    login_ip: Mapped[str] = mapped_column(String(50), nullable=False, comment="登录IP")
    login_city: Mapped[Optional[str]] = mapped_column(String(30), comment="登录城市")
    login_device_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, comment="设备指纹ID")
    login_result: Mapped[str] = mapped_column(
        Enum("成功", "失败", "锁定", name="login_result_enum"),
        nullable=False, comment="登录结果",
    )
    fail_reason: Mapped[Optional[str]] = mapped_column(String(100), comment="失败原因")
    is_new_device: Mapped[int] = mapped_column(Integer, default=0, comment="是否新设备首次登录")
    is_proxy_ip: Mapped[int] = mapped_column(Integer, default=0, comment="是否代理IP")
    session_id: Mapped[Optional[str]] = mapped_column(String(50), comment="会话ID")

    __table_args__ = (
        Index("idx_login_user_id", "user_id"),
        Index("idx_login_time", "login_time"),
        Index("idx_login_device", "login_device_id"),
        Index("idx_login_ip", "login_ip"),
        Index("idx_login_user_time", "user_id", "login_time"),
    )


class DeviceFingerprint(Base):
    """设备指纹表"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备指纹ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="关联用户ID")
    device_type: Mapped[str] = mapped_column(
        Enum("iOS", "Android", "PC", "Web", "Other", name="device_type_enum"),
        nullable=False, comment="设备类型",
    )
    os: Mapped[Optional[str]] = mapped_column(String(50), comment="操作系统")
    os_version: Mapped[Optional[str]] = mapped_column(String(20), comment="OS版本")
    browser: Mapped[Optional[str]] = mapped_column(String(50), comment="浏览器")
    is_rooted: Mapped[int] = mapped_column(Integer, default=0, comment="是否Root越狱")
    is_emulator: Mapped[int] = mapped_column(Integer, default=0, comment="是否模拟器")
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备指纹哈希")
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现时间")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近出现时间")
    associated_users: Mapped[int] = mapped_column(Integer, default=1, comment="关联用户数")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_dev_user_id", "user_id"),
        Index("idx_dev_fingerprint_hash", "fingerprint_hash"),
        Index("idx_dev_associated_users", "associated_users"),
    )


class IpGeoLocation(Base):
    """IP地理位置库"""
    __tablename__ = "ip_geo_location"

    ip_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="IP记录ID")
    ip_cidr: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="IP CIDR段")
    country: Mapped[Optional[str]] = mapped_column(String(50), comment="国家")
    province: Mapped[Optional[str]] = mapped_column(String(30), comment="省份")
    city: Mapped[Optional[str]] = mapped_column(String(30), comment="城市")
    isp: Mapped[Optional[str]] = mapped_column(String(100), comment="运营商")
    is_proxy: Mapped[int] = mapped_column(Integer, default=0, comment="是否代理IP")
    is_tor: Mapped[int] = mapped_column(Integer, default=0, comment="是否Tor出口")
    is_data_center: Mapped[int] = mapped_column(Integer, default=0, comment="是否数据中心IP")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", name="ip_risk_level_enum"),
        default="低", comment="IP风险等级",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_ip_cidr", "ip_cidr"),
        Index("idx_ip_risk_level", "risk_level"),
        Index("idx_ip_city", "city"),
    )


class PasswordChangeLog(Base):
    """密码修改日志表"""
    __tablename__ = "password_change_log"

    pwd_change_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="改密记录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    change_type: Mapped[str] = mapped_column(
        Enum("修改密码", "重置密码", "修改手机号", name="pwd_change_type_enum"),
        nullable=False, comment="变更类型",
    )
    change_ip: Mapped[Optional[str]] = mapped_column(String(50), comment="操作IP")
    change_device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="操作设备ID")
    change_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="变更时间")

    __table_args__ = (
        Index("idx_pwd_user_id", "user_id"),
        Index("idx_pwd_change_time", "change_time"),
    )


class SessionTracking(Base):
    """会话追踪表"""
    __tablename__ = "session_tracking"

    session_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="会话ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="用户ID")
    login_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="登录时间")
    logout_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="登出时间")
    ip_list: Mapped[Optional[str]] = mapped_column(Text, comment="会话内IP变更列表JSON")
    device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="设备指纹ID")
    is_active: Mapped[int] = mapped_column(Integer, default=1, comment="是否活跃")
    ip_change_count: Mapped[int] = mapped_column(Integer, default=0, comment="IP切换次数")

    __table_args__ = (
        Index("idx_session_user_id", "user_id"),
        Index("idx_session_active", "is_active"),
        Index("idx_session_login_time", "login_time"),
    )


# ============================================================
# 第六域: 风控辅助数据 (4 张)
# ============================================================

class HighRiskRegion(Base):
    """高危地区名单表"""
    __tablename__ = "high_risk_region"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="地区ID")
    province: Mapped[str] = mapped_column(String(30), nullable=False, comment="省")
    city: Mapped[Optional[str]] = mapped_column(String(30), comment="市")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", "极高", name="region_risk_level_enum"),
        nullable=False, comment="风险等级",
    )
    risk_category: Mapped[str] = mapped_column(
        Enum("电信诈骗", "洗钱", "赌博", "非法集资", "传销", "其他", name="region_risk_category_enum"),
        nullable=False, comment="风险类型",
    )
    valid_from: Mapped[Date] = mapped_column(Date, nullable=False, comment="生效日期")
    valid_to: Mapped[Optional[Date]] = mapped_column(Date, comment="失效日期 NULL=永久")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_region_city", "province", "city"),
        Index("idx_region_level", "risk_level"),
        Index("idx_region_valid", "valid_from", "valid_to"),
    )


class EnterpriseBlacklist(Base):
    """企业黑名单表"""
    __tablename__ = "enterprise_blacklist"

    enterprise_blacklist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="企业黑名单ID")
    enterprise_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="企业名称")
    credit_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="统一社会信用代码")
    legal_person_hash: Mapped[Optional[str]] = mapped_column(String(128), comment="法定代表人身份证SHA256")
    black_reason: Mapped[str] = mapped_column(Text, nullable=False, comment="列入原因")
    black_source: Mapped[str] = mapped_column(
        Enum("法院失信", "工商吊销", "公安通报", "人行征信", "行内风控", name="black_source_enum"),
        nullable=False, comment="来源",
    )
    black_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="列入时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_ent_blk_credit_code", "credit_code"),
        Index("idx_ent_blk_name", "enterprise_name"),
        Index("idx_ent_blk_legal", "legal_person_hash"),
    )


class FraudCaseRecord(Base):
    """欺诈案件记录表"""
    __tablename__ = "fraud_case_record"

    fraud_case_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="欺诈案件ID")
    fraud_scenario: Mapped[str] = mapped_column(
        Enum("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", name="fraud_scenario_enum"),
        nullable=False, comment="欺诈场景编号F1-F10",
    )
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="关联用户ID")
    involved_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="涉案金额")
    report_source: Mapped[str] = mapped_column(
        Enum("行内风控", "客户投诉", "公安通报", "监管移送", "同业通报", name="fraud_report_source_enum"),
        nullable=False, comment="案件来源",
    )
    report_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="报案发现时间")
    case_status: Mapped[str] = mapped_column(
        Enum("调查中", "已结案", "已移送", name="fraud_case_status_enum"),
        default="调查中", comment="案件状态",
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, comment="备注")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_fraud_user_id", "user_id"),
        Index("idx_fraud_scenario", "fraud_scenario"),
        Index("idx_fraud_report_time", "report_time"),
    )


class RegulatoryReport(Base):
    """监管报送记录表"""
    __tablename__ = "regulatory_report"

    regulatory_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="报送ID")
    reg_type: Mapped[str] = mapped_column(
        Enum("大额交易报告", "可疑交易报告", "客户风险等级", name="reg_type_enum"),
        nullable=False, comment="报送类型",
    )
    ref_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="关联业务ID")
    report_content: Mapped[str] = mapped_column(Text, nullable=False, comment="报告内容JSON")
    report_status: Mapped[str] = mapped_column(
        Enum("待生成", "已生成", "已上报", "已反馈", "补正", name="reg_report_status_enum"),
        default="待生成", comment="报送状态",
    )
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="上报时间")
    feedback_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="反馈时间")
    feedback_result: Mapped[Optional[str]] = mapped_column(String(100), comment="反馈结果")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    __table_args__ = (
        Index("idx_reg_ref_id", "ref_id"),
        Index("idx_reg_type_status", "reg_type", "report_status"),
        Index("idx_reg_submit_time", "submit_time"),
    )
