"""银行信贷风控系统 - 业务表 ORM (17 张).

只读映射银行核心业务实体 (客户/贷款申请/还款/逾期/投诉/联系信息等),
不参与风控决策本身, 但被特征工程和规则引擎查询.
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
# 客户与产品基础
# ============================================================

class CustomerInfo(Base):
    """客户信息表"""
    __tablename__ = "customer_info"

    customer_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="客户ID")
    customer_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户姓名")
    customer_phone: Mapped[str] = mapped_column(String(50), nullable=False, comment="手机号")
    id_card_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="身份证号")
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="状态(正常/冻结)")


class Region(Base):
    """地区表"""
    __tablename__ = "region"

    province: Mapped[str] = mapped_column(String(20), primary_key=True, comment="省")
    city: Mapped[str] = mapped_column(String(20), primary_key=True, comment="市")
    district: Mapped[str] = mapped_column(String(20), primary_key=True, comment="区")


class LoanProductCategory(Base):
    """贷款产品类别表"""
    __tablename__ = "loan_product_category"

    product_category: Mapped[str] = mapped_column(String(20), primary_key=True, comment="贷款产品类别")


class LoanProduct(Base):
    """贷款产品表"""
    __tablename__ = "loan_product"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="产品ID")
    product_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, comment="年利率")
    max_term_month: Mapped[int] = mapped_column(Integer, nullable=False, comment="最长期限(月)")
    max_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="额度上限")
    product_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="贷款产品类别")


# ============================================================
# 贷款申请域
# ============================================================

class LoanStatus(Base):
    """贷款状态表"""
    __tablename__ = "loan_status"

    loan_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="贷款状态")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class LoanApplication(Base):
    """贷款申请表"""
    __tablename__ = "loan_application"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款申请ID")
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    approve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审批时间")
    loan_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="放款时间")
    mature_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="到期时间")
    customer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户ID")
    contact_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="联系信息ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="贷款产品ID")
    loan_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="贷款状态")
    loan_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="申请金额")
    loan_term_month: Mapped[int] = mapped_column(Integer, nullable=False, comment="期限(月)")
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="分期期数")
    annual_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="年收入")
    debt_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="现有负债")
    device_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="设备ID")
    apply_ip_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="申请IP省份")


class LoanInstallment(Base):
    """分期明细表"""
    __tablename__ = "loan_installment"

    installment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="分期明细ID")
    loan_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="贷款申请ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="贷款产品ID")
    installment_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="期数序号")
    due_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="应还金额")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="实还金额")
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="应还日期")
    paid_date: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="实还日期")


# ============================================================
# 还款与逾期域
# ============================================================

class RepaymentStatus(Base):
    """还款状态表"""
    __tablename__ = "repayment_status"

    repayment_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="还款状态")
    is_normal: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否正常")
    is_overdue: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否逾期")
    is_closed: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否结清")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class RepaymentRecord(Base):
    """还款记录表"""
    __tablename__ = "repayment_record"

    repayment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="还款记录ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="还款时间")
    repaid_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="实还时间")
    repayment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="还款金额")
    repayment_category: Mapped[Optional[str]] = mapped_column(
        Enum("正常还款", "提前还款", "逾期还款", name="repayment_category_enum"),
        comment="还款类别",
    )


class LoanRepaymentRel(Base):
    """贷款还款关联表"""
    __tablename__ = "loan_repayment_rel"

    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="贷款申请ID")
    repayment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="还款记录ID")


class OverdueReason(Base):
    """逾期原因表"""
    __tablename__ = "overdue_reason"

    overdue_reason: Mapped[str] = mapped_column(String(100), primary_key=True, comment="逾期原因")
    product_category: Mapped[Optional[str]] = mapped_column(String(20), comment="贷款产品类别")


class OverdueRecord(Base):
    """逾期记录表"""
    __tablename__ = "overdue_record"

    overdue_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="逾期记录ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="结清时间")
    installment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="分期明细ID")
    overdue_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="逾期金额")
    overdue_days: Mapped[int] = mapped_column(Integer, nullable=False, comment="逾期天数")
    overdue_reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="逾期原因")
    overdue_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="逾期状态")
    contact_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="联系信息ID")


class OverdueRepaymentRel(Base):
    """逾期还款关联表"""
    __tablename__ = "overdue_repayment_rel"

    overdue_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="逾期记录ID")
    repayment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="还款记录ID")


# ============================================================
# 联系信息与投诉域
# ============================================================

class ContactInfo(Base):
    """联系信息表"""
    __tablename__ = "contact_info"

    contact_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="联系信息ID")
    customer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户ID")
    contact_person: Mapped[str] = mapped_column(String(50), nullable=False, comment="联系人姓名")
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False, comment="联系电话")
    contact_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省")
    contact_city: Mapped[str] = mapped_column(String(50), nullable=False, comment="市")
    contact_district: Mapped[str] = mapped_column(String(50), nullable=False, comment="区")
    contact_address: Mapped[str] = mapped_column(String(50), nullable=False, comment="详细地址")
    emergency_name: Mapped[Optional[str]] = mapped_column(String(50), comment="紧急联系人姓名")
    emergency_phone: Mapped[Optional[str]] = mapped_column(String(50), comment="紧急联系人电话")


class ComplaintContent(Base):
    """投诉内容对照表"""
    __tablename__ = "complaint_content"

    complaint_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="投诉类型")
    complaint_content: Mapped[str] = mapped_column(String(100), primary_key=True, comment="投诉内容")


class ComplaintRecord(Base):
    """投诉记录表"""
    __tablename__ = "complaint_record"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="投诉记录ID")
    customer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户ID")
    loan_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="贷款申请ID")
    complaint_content: Mapped[str] = mapped_column(String(500), nullable=False, comment="投诉内容")
    complaint_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投诉时间")


class BankBranch(Base):
    """银行网点表"""
    __tablename__ = "bank_branch"

    branch_name: Mapped[str] = mapped_column(String(50), primary_key=True, comment="银行网点名称")