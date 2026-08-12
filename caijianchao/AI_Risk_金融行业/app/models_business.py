"""
金融风控系统 - 业务表 ORM
只读映射现有金融业务系统的核心实体 (账户/交易/贷款/信用卡/征信等)
不参与风控决策本身, 但被特征工程和规则引擎查询
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    SmallInteger,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 账户域
# ============================================================

class AccountInfo(Base):
    """账户信息表"""
    __tablename__ = "account_info"

    account_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="账户ID")
    user_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户姓名")
    id_card_no: Mapped[str] = mapped_column(String(18), nullable=False, comment="身份证号(加密)")
    phone_no: Mapped[str] = mapped_column(String(11), nullable=False, comment="手机号(加密)")
    account_type: Mapped[Optional[str]] = mapped_column(
        Enum("个人", "企业", name="account_type_enum"),
        default="个人", comment="账户类型",
    )
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    kyc_level: Mapped[Optional[str]] = mapped_column(
        Enum("未认证", "基础认证", "高级认证", name="kyc_level_enum"),
        default="未认证", comment="KYC认证等级",
    )
    account_status: Mapped[Optional[str]] = mapped_column(
        Enum("正常", "冻结", "销户", name="account_status_enum"),
        default="正常", comment="账户状态",
    )
    risk_level: Mapped[Optional[str]] = mapped_column(
        Enum("低", "中", "高", "黑名单", name="account_risk_level_enum"),
        default="低", comment="当前风险等级",
    )
    monthly_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="月收入(元)")
    employment_status: Mapped[Optional[str]] = mapped_column(String(20), comment="职业状态")
    total_in_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), default=0, comment="历史累计入账金额")
    last_txn_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最后一次交易时间")


class UserInfo(Base):
    """客户基础信息表 (符合央行KYC与反洗钱要求)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="客户ID")
    full_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="法定姓名")
    id_card_no: Mapped[str] = mapped_column(String(100), nullable=False, comment="身份证号(加密)")
    phone_no: Mapped[str] = mapped_column(String(100), nullable=False, comment="手机号(加密)")
    email: Mapped[Optional[str]] = mapped_column(String(100), comment="电子邮箱")
    gender: Mapped[Optional[str]] = mapped_column(Enum("M", "F", "U", name="gender_enum"), default="U", comment="性别")
    birth_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出生日期")
    nationality: Mapped[Optional[str]] = mapped_column(String(20), default="CN", comment="国籍")
    education: Mapped[Optional[str]] = mapped_column(String(20), comment="学历")
    occupation: Mapped[Optional[str]] = mapped_column(String(50), comment="职业类别")
    annual_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="年收入")
    marital_status: Mapped[Optional[str]] = mapped_column(
        Enum("未婚", "已婚", "离异", "丧偶", name="marital_status_enum"), comment="婚姻状况",
    )
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(50), comment="紧急联系人姓名")
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(100), comment="紧急联系人电话")
    kyc_status: Mapped[Optional[str]] = mapped_column(
        Enum("未认证", "基础认证", "高级认证", name="kyc_status_enum"),
        default="未认证", comment="KYC认证等级",
    )
    risk_tolerance: Mapped[Optional[str]] = mapped_column(
        Enum("保守型", "稳健型", "进取型", name="risk_tolerance_enum"), comment="风险承受能力",
    )
    is_politically_exposed: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否PEP")
    register_source: Mapped[Optional[str]] = mapped_column(String(20), default="APP", comment="注册渠道")
    register_ip: Mapped[Optional[str]] = mapped_column(String(45), comment="注册IP")
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    last_login_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最后登录时间")
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="更新时间")


# ============================================================
# 交易域
# ============================================================

class TransactionType(Base):
    """交易类型表"""
    __tablename__ = "transaction_type"

    txn_type_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment="交易类型编码")
    txn_type_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="交易类型名称")
    is_credit: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否贷记(入账)")
    is_debit: Mapped[Optional[int]] = mapped_column(SmallInteger, default=1, comment="是否借记(出账)")
    is_cash: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否现金交易")


class ProductChannel(Base):
    """渠道表"""
    __tablename__ = "product_channel"

    channel_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment="渠道编码")
    channel_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="渠道名称")
    channel_type: Mapped[Optional[str]] = mapped_column(
        Enum("线上", "线下", "移动", name="channel_type_enum"),
        default="线上", comment="渠道类型",
    )
    is_counter: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否柜面渠道")


class TransactionOrder(Base):
    """交易订单主表"""
    __tablename__ = "transaction_order"

    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="交易流水号")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="发起方账户ID")
    counterparty_account: Mapped[Optional[str]] = mapped_column(String(50), comment="对手方账户ID")
    counterparty_name: Mapped[Optional[str]] = mapped_column(String(50), comment="对手方户名")
    txn_type_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="交易类型")
    channel_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="交易渠道")
    txn_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="交易金额")
    txn_currency: Mapped[Optional[str]] = mapped_column(String(3), default="CNY", comment="币种")
    txn_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="交易完成时间")
    request_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="用户发起请求时间")
    txn_status: Mapped[Optional[str]] = mapped_column(
        Enum("处理中", "成功", "失败", "冲正", "可疑冻结", name="txn_status_enum"),
        default="处理中", comment="交易状态",
    )
    is_overseas: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否境外交易")
    country_code: Mapped[Optional[str]] = mapped_column(String(10), default="CN", comment="交易对手国家代码")
    device_id: Mapped[Optional[str]] = mapped_column(String(100), comment="设备指纹ID")
    device_env: Mapped[Optional[str]] = mapped_column(String(50), comment="设备环境")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), comment="交易IP地址")
    gps_location: Mapped[Optional[str]] = mapped_column(String(100), comment="GPS位置")
    merchant_id: Mapped[Optional[str]] = mapped_column(String(50), comment="商户号")
    remark: Mapped[Optional[str]] = mapped_column(String(500), comment="备注/用途说明")


class AccountBalanceLog(Base):
    """账户余额变动日志表"""
    __tablename__ = "account_balance_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="账户ID")
    txn_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联交易流水号")
    before_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="变动前余额")
    change_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="变动金额")
    after_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="变动后余额")
    change_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="变动时间")
    operator: Mapped[Optional[str]] = mapped_column(String(50), default="SYSTEM", comment="操作方")


# ============================================================
# 信贷域
# ============================================================

class LoanInfo(Base):
    """贷款信息表"""
    __tablename__ = "loan_info"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款合同号")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="借款人ID")
    loan_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="贷款金额")
    loan_term: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, comment="年化利率")
    loan_purpose: Mapped[Optional[str]] = mapped_column(String(100), comment="贷款用途")
    approve_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="放款时间")
    due_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="到期时间")
    repay_status: Mapped[Optional[str]] = mapped_column(
        Enum("正常", "逾期", "结清", "核销", name="repay_status_enum"),
        default="正常", comment="还款状态",
    )
    overdue_days: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="当前逾期天数")
    remaining_principal: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), comment="剩余本金")
    lender_org: Mapped[Optional[str]] = mapped_column(String(100), comment="贷款机构")


class RepaymentRecord(Base):
    """还款记录表"""
    __tablename__ = "repayment_record"

    repay_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="还款记录ID")
    loan_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联贷款ID")
    repay_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="还款金额")
    repay_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="还款时间")
    repay_type: Mapped[Optional[str]] = mapped_column(
        Enum("正常还款", "提前还款", "逾期还款", name="repay_type_enum"),
        default="正常还款", comment="还款类型",
    )
    is_late: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否逾期")
    late_days: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="逾期天数")


class CreditCardInfo(Base):
    """信用卡额度信息表"""
    __tablename__ = "credit_card_info"

    card_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="信用卡卡号(加密)")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="账户ID")
    total_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, comment="总额度")
    used_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), default=0, comment="已用额度")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="额度更新时间")


class CreditInquiryLog(Base):
    """征信查询记录表"""
    __tablename__ = "credit_inquiry_log"

    inquiry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="查询ID")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="账户ID")
    inquiry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="查询时间")
    inquiry_reason: Mapped[str] = mapped_column(
        Enum("贷款审批", "信用卡审批", "贷后管理", "本人查询", name="inquiry_reason_enum"),
        nullable=False, comment="查询原因",
    )
    inquiry_org: Mapped[str] = mapped_column(String(100), nullable=False, comment="查询机构")
    is_approved: Mapped[Optional[int]] = mapped_column(SmallInteger, default=0, comment="是否批贷/批卡")


# ============================================================
# 辅助域
# ============================================================

class Blacklist(Base):
    """黑名单/制裁名单表"""
    __tablename__ = "blacklist"

    blacklist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    target_type: Mapped[str] = mapped_column(
        Enum("身份证", "手机号", "账户", "IP", "设备ID", "国家地区", name="blacklist_target_type_enum"),
        nullable=False, comment="名单类型",
    )
    target_value: Mapped[str] = mapped_column(String(100), nullable=False, comment="名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(200), comment="列入原因")
    source: Mapped[Optional[str]] = mapped_column(String(50), comment="来源")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间")


class AddressHistory(Base):
    """地址/归属地历史记录表"""
    __tablename__ = "address_history"

    address_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="地址ID")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="账户ID")
    address_type: Mapped[str] = mapped_column(
        Enum("注册地址", "常用地址", "交易IP属地", "GPS位置", name="address_type_enum"),
        nullable=False, comment="地址类型",
    )
    province: Mapped[Optional[str]] = mapped_column(String(20), comment="省")
    city: Mapped[Optional[str]] = mapped_column(String(20), comment="市")
    district: Mapped[Optional[str]] = mapped_column(String(20), comment="区")
    detail_address: Mapped[Optional[str]] = mapped_column(String(200), comment="详细地址")
    ip_segment: Mapped[Optional[str]] = mapped_column(String(20), comment="IP段")
    first_seen_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次发现时间")
    last_seen_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最后发现时间")
    use_count: Mapped[Optional[int]] = mapped_column(Integer, default=1, comment="使用次数")


class UserOperationLog(Base):
    """用户操作日志表"""
    __tablename__ = "user_operation_log"

    op_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="操作ID")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="账户ID")
    op_type: Mapped[str] = mapped_column(
        Enum("登录", "修改密码", "修改手机号", "修改邮箱", "找回密码",
             "绑定银行卡", "解绑设备", "修改支付密码", name="op_type_enum"),
        nullable=False, comment="操作类型",
    )
    op_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="操作时间")
    op_result: Mapped[Optional[str]] = mapped_column(
        Enum("成功", "失败", name="op_result_enum"),
        default="成功", comment="操作结果",
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), comment="IP地址")
    device_id: Mapped[Optional[str]] = mapped_column(String(100), comment="设备ID")
    client_type: Mapped[Optional[str]] = mapped_column(String(20), comment="客户端类型")


class AmlSuspiciousReport(Base):
    """反洗钱可疑交易报告表"""
    __tablename__ = "aml_suspicious_report"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="报告ID")
    txn_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="交易流水号")
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="账户ID")
    report_type: Mapped[str] = mapped_column(
        Enum("大额交易", "可疑交易", "制裁名单匹配", name="report_type_enum"),
        nullable=False, comment="报告类型",
    )
    trigger_rule: Mapped[str] = mapped_column(String(100), nullable=False, comment="触发规则名称")
    report_content: Mapped[Optional[str]] = mapped_column(Text, comment="详细描述")
    report_status: Mapped[Optional[str]] = mapped_column(
        Enum("待上报", "已上报", "已排除", name="report_status_enum"),
        default="待上报", comment="报告状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    report_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="上报时间")
    operator: Mapped[Optional[str]] = mapped_column(String(50), comment="操作人")
