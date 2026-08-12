"""
银行信贷风控系统 - 业务表 ORM (17 张)

业务边界: 信用卡 / 贷款 / 转账 / 登录 4 大场景, 覆盖信贷全生命周期
  - 贷前: 借款人主档 + 企业档案 + 征信 + 收入三源交叉核验 (能不能借)
  - 贷中: 贷款申请 -> 合同 -> 放款 + 抵押物 / 担保 (钱怎么付)
  - 贷后: 还款计划 / 还款流水 / 逾期 + 交易资金流向监控 (钱收不收得回)
  - 反欺诈: 设备指纹 / IP 地理库 / 登录日志 / 关联关系图谱 / 行业黑名单

【为后续风控特征计算做的设计】
1. 时间字段 + (user_id, time) 复合索引
   - loan_application(user_id, apply_time) -> "近30天申请笔数 / 申请频率"
   - repayment_plan(user_id, status)       -> "当前逾期期数 / 近24月逾期次数"
   - transaction(user_id, txn_time)        -> "近30天入账总额 / 资金回流窗口"
   - login_log(user_id, login_time)        -> "近7天登录次数 / 凌晨登录占比"
2. 冗余 user_id 到子表 (repayment_plan / repayment_record / credit_report 等),
   避免特征计算必须 join 回主表
3. 哈希字段支撑关联查询
   - id_card_hash / account_no_hash / fingerprint_hash / cert_no_hash
     -> 同身份证 / 同卡 / 同设备 / 一房多贷 的团伙识别 (PII 脱敏合规)
4. 枚举值统一用中文业务词, 与 DDL / 规则引擎条件保持一致
5. 状态字段用 VARCHAR 存业务状态, 便于演进, 不锁死在 ENUM
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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now()


# ============================================================
# 贷前: 客户主档 (个人 / 企业)
# ============================================================

class UserInfo(Base):
    """借款人主档表 (个人客户)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="借款人ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    gender: Mapped[str] = mapped_column(
        Enum("男", "女", "未知", name="gender_enum"),
        nullable=False, server_default="未知", comment="性别",
    )
    birth_date: Mapped[datetime] = mapped_column(Date, nullable=False, comment="出生日期")
    age: Mapped[int] = mapped_column(Integer, nullable=False, comment="年龄(冗余, 特征直接用)")
    id_card_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="身份证号SHA256哈希(脱敏)")
    mobile: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    marital_status: Mapped[str] = mapped_column(
        Enum("未婚", "已婚", "离异", "丧偶", "未知", name="marital_status_enum"),
        nullable=False, server_default="未知", comment="婚姻状况",
    )
    education: Mapped[str] = mapped_column(String(20), nullable=False, comment="学历")
    occupation: Mapped[str] = mapped_column(String(50), nullable=False, comment="职业")
    employer_name: Mapped[Optional[str]] = mapped_column(String(100), comment="工作单位")
    employer_category: Mapped[Optional[str]] = mapped_column(String(50), comment="单位性质")
    industry_code: Mapped[Optional[str]] = mapped_column(String(20), comment="行业代码")
    household_province: Mapped[Optional[str]] = mapped_column(String(20), comment="户籍省")
    household_city: Mapped[Optional[str]] = mapped_column(String(20), comment="户籍市")
    household_district: Mapped[Optional[str]] = mapped_column(String(20), comment="户籍区县")
    household_address: Mapped[Optional[str]] = mapped_column(String(200), comment="户籍详细地址")
    living_province: Mapped[Optional[str]] = mapped_column(String(20), comment="居住省")
    living_city: Mapped[Optional[str]] = mapped_column(String(20), comment="居住市")
    living_district: Mapped[Optional[str]] = mapped_column(String(20), comment="居住区县")
    living_address: Mapped[Optional[str]] = mapped_column(String(200), comment="居住详细地址")
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0.00", comment="申报月收入")
    verified_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0.00", comment="核验后月收入")
    income_source: Mapped[str] = mapped_column(
        Enum("受雇", "自雇", "经营", "自由职业", "其他", name="income_source_enum"),
        nullable=False, server_default="其他", comment="收入来源",
    )
    credit_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="600", comment="行内信用分(0-1000)")
    kyc_level: Mapped[str] = mapped_column(
        Enum("未认证", "L1", "L2", "L3", name="kyc_level_enum"),
        nullable=False, server_default="未认证", comment="KYC等级(实名认证深度)",
    )
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开户时间")
    account_age_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="开户天数(冗余)")
    is_employee: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否本行员工(内部欺诈场景)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("id_card_hash", name="uk_user_id_card_hash"),
        UniqueConstraint("mobile", name="uk_user_mobile"),
        Index("idx_user_kyc_level", "kyc_level"),
        Index("idx_user_register_at", "register_at"),
        Index("idx_user_living", "living_province", "living_city"),
    )


class EnterpriseInfo(Base):
    """企业经营档案表 (经营性贷款借款人)"""
    __tablename__ = "enterprise_info"

    ent_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="企业ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="法定代表人用户ID")
    ent_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="企业名称")
    credit_code: Mapped[str] = mapped_column(String(18), nullable=False, comment="统一社会信用代码")
    legal_person: Mapped[str] = mapped_column(String(50), nullable=False, comment="法定代表人")
    reg_date: Mapped[datetime] = mapped_column(Date, nullable=False, comment="成立日期")
    business_years: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="经营年限(冗余)")
    industry: Mapped[str] = mapped_column(String(50), nullable=False, comment="所属行业")
    reg_capital: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="注册资本")
    paid_in_capital: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="实缴资本")
    annual_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="年营业收入")
    annual_tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="年纳税额")
    employee_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="员工人数")
    operation_status: Mapped[str] = mapped_column(
        Enum("存续", "在业", "吊销", "注销", "迁出", name="operation_status_enum"),
        nullable=False, server_default="存续", comment="经营状态",
    )
    reg_address: Mapped[Optional[str]] = mapped_column(String(200), comment="注册地址")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("credit_code", name="uk_ent_credit_code"),
        Index("idx_ent_user_id", "user_id"),
    )


class BankAccount(Base):
    """银行账户表 (储蓄卡/信用卡/对公账户)"""
    __tablename__ = "bank_account"

    account_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="账户ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    account_no_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="卡号SHA256哈希(脱敏)")
    account_no_tail: Mapped[str] = mapped_column(String(4), nullable=False, comment="卡号尾号4位(展示用)")
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="开户行联行号")
    bank_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="开户行名称")
    account_type: Mapped[str] = mapped_column(
        Enum("储蓄卡", "信用卡", "对公账户", name="account_type_enum"),
        nullable=False, comment="账户类型",
    )
    card_status: Mapped[str] = mapped_column(
        Enum("正常", "冻结", "挂失", "销户", name="card_status_enum"),
        nullable=False, server_default="正常", comment="卡片状态",
    )
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0.00", comment="信用卡额度(储蓄卡为0)")
    open_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开户时间")
    account_age_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="开户天数(冗余)")
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否默认还款账户")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("account_no_hash", name="uk_account_no_hash"),
        Index("idx_account_user_id", "user_id"),
        Index("idx_account_type", "account_type"),
    )


# ============================================================
# 贷中: 申请 -> 审批 -> 合同 -> 放款
# ============================================================

class LoanApplication(Base):
    """贷款申请表"""
    __tablename__ = "loan_application"

    application_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    product_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="产品编码")
    product_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品名称")
    apply_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="申请金额")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    purpose: Mapped[str] = mapped_column(
        Enum("消费", "经营", "购房", "购车", "装修", "教育", "医疗", "其他", name="loan_purpose_enum"),
        nullable=False, comment="贷款用途",
    )
    guarantee_type: Mapped[str] = mapped_column(
        Enum("信用", "抵押", "质押", "保证", "组合", name="guarantee_type_enum"),
        nullable=False, server_default="信用", comment="担保方式",
    )
    repay_type: Mapped[str] = mapped_column(
        Enum("等额本息", "等额本金", "先息后本", "一次性还本付息", name="repay_type_enum"),
        nullable=False, server_default="等额本息", comment="还款方式",
    )
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="申报月收入")
    monthly_debt: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0.00", comment="月负债")
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.0000", comment="债务收入比DTI=月负债/月收入")
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    channel: Mapped[str] = mapped_column(
        Enum("线上APP", "网上银行", "线下网点", "第三方平台", name="loan_channel_enum"),
        nullable=False, server_default="线上APP", comment="申请渠道",
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="申请设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="申请IP")
    geo: Mapped[Optional[str]] = mapped_column(String(50), comment="IP归属地")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="进件", comment="申请状态(进件/反欺诈核查/准入授信/审批中/审批通过/审批拒绝/签约/放款/结清)")
    reject_reason: Mapped[Optional[str]] = mapped_column(String(200), comment="拒绝原因")
    approval_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), comment="审批通过金额")
    approval_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), comment="审批年化利率")
    is_repay_plan_generated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否已生成还款计划")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_loan_app_user_time", "user_id", "apply_time"),
        Index("idx_loan_app_status", "status"),
        Index("idx_loan_app_product", "product_code"),
        Index("idx_loan_app_device", "device_id"),
        Index("idx_loan_app_ip", "ip"),
        Index("idx_loan_app_time", "apply_time"),
    )


class LoanContract(Base):
    """贷款合同表 (借据)"""
    __tablename__ = "loan_contract"

    contract_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="合同ID")
    application_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    contract_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同编号")
    product_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="产品编码(冗余)")
    product_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品名称(冗余)")
    loan_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="放款金额")
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, comment="年化利率")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    repay_type: Mapped[str] = mapped_column(
        Enum("等额本息", "等额本金", "先息后本", "一次性还本付息", name="contract_repay_type_enum"),
        nullable=False, comment="还款方式",
    )
    disbursement_date: Mapped[datetime] = mapped_column(Date, nullable=False, comment="放款日期")
    maturity_date: Mapped[datetime] = mapped_column(Date, nullable=False, comment="到期日期")
    repay_account_id: Mapped[Optional[str]] = mapped_column(String(50), comment="还款账户ID")
    disbursement_account_id: Mapped[Optional[str]] = mapped_column(String(50), comment="放款账户ID")
    is_trustee_payment: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否受托支付")
    trustee_payee: Mapped[Optional[str]] = mapped_column(String(100), comment="受托支付收款人")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="正常", comment="合同状态(正常/逾期/结清/核销/不良)")
    overdue_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="当前最长逾期天数")
    current_overdue_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="当前逾期金额")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("application_id", name="uk_contract_application"),
        UniqueConstraint("contract_no", name="uk_contract_no"),
        Index("idx_contract_user_id", "user_id"),
        Index("idx_contract_repay_account", "repay_account_id"),
        Index("idx_contract_status", "status"),
        Index("idx_contract_disburse_date", "disbursement_date"),
    )


# ============================================================
# 贷后: 还款计划 / 还款流水 / 逾期
# ============================================================

class RepaymentPlan(Base):
    """还款计划表 (每期一条)"""
    __tablename__ = "repayment_plan"

    plan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="还款计划ID")
    contract_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID(冗余, 特征直接用)")
    period_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="期数(第N期)")
    due_date: Mapped[datetime] = mapped_column(Date, nullable=False, comment="应还日期")
    principal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="应还本金")
    interest: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="应还利息")
    total_due: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="应还总额")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="未到期", comment="状态(未到期/待还/已还/逾期)")
    overdue_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="逾期天数")
    actual_repay_date: Mapped[Optional[datetime]] = mapped_column(Date, comment="实际还款日期")
    actual_repay_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), comment="实际还款金额")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("contract_id", "period_no", name="uk_plan_contract_period"),
        Index("idx_plan_user_status", "user_id", "status"),
        Index("idx_plan_due_date", "due_date"),
        Index("idx_plan_status", "status"),
    )


class RepaymentRecord(Base):
    """还款流水表"""
    __tablename__ = "repayment_record"

    record_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="还款记录ID")
    contract_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同ID")
    plan_id: Mapped[Optional[str]] = mapped_column(String(50), comment="还款计划ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID(冗余)")
    repay_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="还款总额")
    principal_part: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="还本部分")
    interest_part: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="还息部分")
    penalty_part: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="罚息部分")
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="自动扣款", comment="还款渠道")
    repay_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="还款时间")
    is_success: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", comment="是否成功")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_repay_user_time", "user_id", "repay_time"),
        Index("idx_repay_contract", "contract_id"),
        Index("idx_repay_plan", "plan_id"),
        Index("idx_repay_success", "is_success"),
    )


# ============================================================
# 贷前风控数据: 征信 / 收入核验 / 抵押 / 担保
# ============================================================

class CreditReport(Base):
    """征信报告快照表 (每次授权查询一份)"""
    __tablename__ = "credit_report"

    report_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="征信报告ID")
    application_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    report_date: Mapped[datetime] = mapped_column(Date, nullable=False, comment="报告日期")
    credit_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="征信分(0-1000)")
    overdue_24m_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="近24月累计逾期次数")
    overdue_24m_max_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="近24月最长逾期月数")
    current_overdue_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="当前逾期账户数")
    current_overdue_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="当前逾期金额")
    five_level_class: Mapped[str] = mapped_column(String(10), nullable=False, server_default="正常", comment="五级分类(正常/关注/次级/可疑/损失)")
    has_judgement: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否涉诉")
    is_executed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否被执行人")
    is_discredited: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否失信被执行人")
    is_daichang: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否代偿")
    guarantee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="对外担保余额")
    outstanding_loan_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="未结清贷款笔数")
    credit_card_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="未销户信用卡数")
    recent_6m_hard_query_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="近6月硬查询次数(贷款审批/信用卡审批)")
    recent_1m_query_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="近1月查询次数")
    open_account_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="已开立账户数")
    settled_account_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="已结清账户数")
    first_loan_date: Mapped[Optional[datetime]] = mapped_column(Date, comment="首笔贷款日期")
    loan_history_years: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False, server_default="0.0", comment="征信历史年限")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_credit_user_report", "user_id", "report_date"),
        Index("idx_credit_application", "application_id"),
        Index("idx_credit_report_date", "report_date"),
    )


class IncomeVerify(Base):
    """收入三源交叉核验表 (收入证明 / 银行流水 / 完税证明)"""
    __tablename__ = "income_verify"

    verify_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="核验ID")
    application_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    declared_monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="申报月收入")
    salary_proof_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment="收入证明月收入")
    bank_flow_avg_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment="银行流水月均入账")
    tax_proof_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment="完税证明推算月收入")
    verified_monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="核验后月收入")
    has_payroll_record: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否有代发工资记录")
    bank_flow_min_balance_3m: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="近3月账户最低余额")
    bank_flow_total_in_6m: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0.00", comment="近6月入账总额")
    cross_check_result: Mapped[str] = mapped_column(String(20), nullable=False, server_default="一致", comment="三源交叉结果(一致/轻微偏差/显著偏差/无法核验)")
    verify_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="核验时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_income_verify_app", "application_id"),
        Index("idx_income_verify_user", "user_id"),
    )


class Collateral(Base):
    """抵押物质押表 (含一房多贷查重)"""
    __tablename__ = "collateral"

    collateral_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="抵押物ID")
    application_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联申请ID")
    contract_id: Mapped[Optional[str]] = mapped_column(String(50), comment="关联合同ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    collateral_type: Mapped[str] = mapped_column(
        Enum("不动产", "车辆", "存单", "应收账款", "其他", name="collateral_type_enum"),
        nullable=False, comment="抵押物类型",
    )
    cert_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="权证编号(不动产权证号/VIN/存单号)")
    cert_no_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="权证编号哈希(一房多贷查重)")
    property_address: Mapped[Optional[str]] = mapped_column(String(200), comment="不动产地址")
    owner_name: Mapped[Optional[str]] = mapped_column(String(50), comment="权利人姓名")
    eval_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="评估价值")
    mortgage_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000", comment="抵押率=贷款金额/评估价值")
    query_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="无查封", comment="不动产查询结果(无查封/已查封/已抵押/重复抵押)")
    pledge_time: Mapped[Optional[datetime]] = mapped_column(Date, comment="抵押设立日期")
    release_time: Mapped[Optional[datetime]] = mapped_column(Date, comment="解押日期")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="在押", comment="状态(在押/已解押)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_collateral_cert_hash", "cert_no_hash"),
        Index("idx_collateral_user", "user_id"),
        Index("idx_collateral_application", "application_id"),
    )


class Guarantee(Base):
    """担保关系表 (关联担保 / 互保 / 图谱边)"""
    __tablename__ = "guarantee"

    guarantee_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="担保ID")
    contract_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    guarantor_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="担保人用户ID")
    guarantor_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="担保人姓名(冗余)")
    guarantee_type: Mapped[str] = mapped_column(
        Enum("连带责任保证", "一般保证", "抵押担保", "质押担保", name="guarantee_type_enum"),
        nullable=False, comment="担保方式",
    )
    guarantee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="担保金额")
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="亲属", comment="与借款人关系(亲属/同事/朋友/互保/关联企业/其他)")
    sign_time: Mapped[datetime] = mapped_column(Date, nullable=False, comment="签署日期")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="有效", comment="状态(有效/解除/履行完毕/代偿中)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_guarantee_user", "user_id"),
        Index("idx_guarantee_guarantor", "guarantor_id"),
        Index("idx_guarantee_contract", "contract_id"),
    )


# ============================================================
# 账户/设备/行为: 转账 / 登录 / 设备 / IP
# ============================================================

class Transaction(Base):
    """账户交易流水表 (转账/支付/资金流向监控)"""
    __tablename__ = "transaction"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    from_account_id: Mapped[Optional[str]] = mapped_column(String(50), comment="转出账户ID")
    to_account_id: Mapped[Optional[str]] = mapped_column(String(50), comment="转入账户ID(取现/消费可为空)")
    counterparty_name: Mapped[Optional[str]] = mapped_column(String(100), comment="对手方名称")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="交易金额")
    txn_type: Mapped[str] = mapped_column(
        Enum("转账", "消费", "取现", "代扣", "理财", "还款", "工资入账", "退款", "其他", name="txn_type_enum"),
        nullable=False, comment="交易类型",
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False, server_default="手机银行", comment="交易渠道")
    txn_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="交易时间")
    device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="IP")
    geo: Mapped[Optional[str]] = mapped_column(String(50), comment="IP归属地")
    is_suspicious: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="异常标记(资金回流/涉赌涉诈)")
    remark: Mapped[Optional[str]] = mapped_column(String(200), comment="备注")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_txn_from_time", "from_account_id", "txn_time"),
        Index("idx_txn_to_time", "to_account_id", "txn_time"),
        Index("idx_txn_user_time", "user_id", "txn_time"),
        Index("idx_txn_device", "device_id"),
        Index("idx_txn_ip", "ip"),
        Index("idx_txn_time", "txn_time"),
    )


class LoginLog(Base):
    """登录日志表"""
    __tablename__ = "login_log"

    login_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="登录ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    device_id: Mapped[Optional[str]] = mapped_column(String(50), comment="设备ID")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="登录IP")
    geo: Mapped[Optional[str]] = mapped_column(String(50), comment="IP归属地")
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="APP", comment="登录渠道")
    success: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", comment="是否成功")
    login_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="登录时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_login_user_time", "user_id", "login_time"),
        Index("idx_login_device", "device_id"),
        Index("idx_login_ip", "ip"),
        Index("idx_login_time", "login_time"),
    )


class DeviceFingerprint(Base):
    """设备指纹表 (设备多人共用识别)"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="所属用户ID")
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="设备指纹哈希")
    os: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作系统")
    browser: Mapped[Optional[str]] = mapped_column(String(50), comment="浏览器")
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="手机", comment="设备类型(手机/平板/PC)")
    is_root: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否Root/越狱")
    mac_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="MAC哈希")
    imei_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="IMEI哈希")
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现时间")
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近出现时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_device_user", "user_id"),
        Index("idx_device_fp_hash", "fingerprint_hash"),
    )


class IpGeoLocation(Base):
    """IP 地理库表 (代理/Tor/归属地识别)"""
    __tablename__ = "ip_geo_location"

    ip: Mapped[str] = mapped_column(String(50), primary_key=True, comment="IP地址")
    country: Mapped[str] = mapped_column(String(20), nullable=False, server_default="中国", comment="国家")
    province: Mapped[str] = mapped_column(String(20), nullable=False, comment="省份")
    city: Mapped[str] = mapped_column(String(20), nullable=False, comment="城市")
    isp: Mapped[str] = mapped_column(String(30), nullable=False, comment="运营商")
    is_proxy: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否代理IP")
    is_tor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否Tor出口")
    is_mobile: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否移动网络")
    is_abroad: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="是否境外IP")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )


# ============================================================
# 反欺诈: 行业黑名单 / 关联关系图谱
# ============================================================

class BlacklistExtra(Base):
    """银行业务黑名单扩展表 (在 risk_blacklist 之外按行业补充)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    type: Mapped[str] = mapped_column(
        Enum("设备指纹", "IP", "银行卡号", "身份证号", "手机号", "对公账户", "统一社会信用代码", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值(敏感值存哈希)")
    reason: Mapped[Optional[str]] = mapped_column(String(200), comment="加入原因")
    source: Mapped[str] = mapped_column(String(50), nullable=False, server_default="内部案件", comment="来源")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_blacklist_type_value", "type", "value"),
        Index("idx_blacklist_expire", "expire_time"),
    )


class UserRelation(Base):
    """用户关联关系表 (知识图谱反欺诈: 同设备/同手机/同地址/互保/资金往来)"""
    __tablename__ = "user_relation"

    relation_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="关系ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID(A)")
    related_user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联用户ID(B)")
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="关系类型(共享设备/共享手机/共享地址/亲属/同事/互保/资金往来/共享收款账户)")
    detail_value: Mapped[Optional[str]] = mapped_column(String(100), comment="共享的具体值(device_id/手机号/地址/账户)")
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="设备", comment="关系来源(设备/担保/交易/申请/外部)")
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次发现时间")
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近发现时间")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", comment="是否有效")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=_now, onupdate=_now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_relation_user", "user_id"),
        Index("idx_relation_related", "related_user_id"),
        Index("idx_relation_type", "relation_type"),
        Index("idx_relation_detail", "detail_value"),
    )
