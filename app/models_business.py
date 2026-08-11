"""
医疗风控系统 - 业务表 ORM (8 张)
只读映射医疗业务系统的核心实体 (参保人/医院/医生/挂号/处方/医保结算/药品订单/扩展黑名单)
不参与风控决策本身, 但被特征工程和规则引擎查询
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
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 参保人 / 机构 / 医师基础
# ============================================================

class UserInfo(Base):
    """参保人信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    id_card_hash: Mapped[str] = mapped_column(String(100), nullable=False, comment="身份证号哈希")
    medical_card_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="医保卡号")
    phone_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="手机号")
    insurance_type: Mapped[str] = mapped_column(
        Enum("城镇职工", "城乡居民", name="insurance_type_enum"),
        nullable=False, comment="参保类型",
    )
    insure_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="参保省")
    insure_city: Mapped[str] = mapped_column(String(20), nullable=False, comment="参保市")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="参保注册时间")


class Hospital(Base):
    """医院档案表"""
    __tablename__ = "hospital"

    hospital_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="医院ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="医院名称")
    level: Mapped[str] = mapped_column(String(20), nullable=False, comment="医院级别(三甲/二甲等)")
    province: Mapped[str] = mapped_column(String(20), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(20), nullable=False, comment="市")
    is_insured: Mapped[int] = mapped_column(Integer, default=1, comment="是否医保定点(1=是)")


class Doctor(Base):
    """医生档案表"""
    __tablename__ = "doctor"

    doctor_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="医生ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="所属医院ID")
    department: Mapped[str] = mapped_column(String(50), nullable=False, comment="科室")
    title: Mapped[str] = mapped_column(String(20), nullable=False, comment="职称")
    license_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="执业证号")


# ============================================================
# 挂号域
# ============================================================

class Appointment(Base):
    """挂号记录表 (对应电商"订单")"""
    __tablename__ = "appointment"

    appt_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="挂号ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="医院ID")
    department: Mapped[str] = mapped_column(String(50), nullable=False, comment="科室")
    doctor_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="医生ID")
    appt_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="就诊时间")
    pay_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="挂号费")
    appt_status: Mapped[str] = mapped_column(
        Enum("已预约", "已就诊", "已取消", name="appt_status_enum"),
        nullable=False, default="已预约", comment="挂号状态",
    )
    cancel_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="取消时间")


# ============================================================
# 处方域
# ============================================================

class Prescription(Base):
    """处方单表"""
    __tablename__ = "prescription"

    rx_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="处方ID")
    doctor_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="开方医生ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="医院ID")
    diagnosis_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="诊断编码(ICD-10)")
    diagnosis_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="诊断名称")
    items: Mapped[Optional[str]] = mapped_column(Text, comment="药品明细(JSON)")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="处方总金额")
    is_insured: Mapped[int] = mapped_column(Integer, default=1, comment="是否医保支付(1=是)")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开方时间")


# ============================================================
# 医保结算域
# ============================================================

class InsuranceClaim(Base):
    """医保结算单表 (对应电商"支付")"""
    __tablename__ = "insurance_claim"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="结算ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="医院ID")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="总费用")
    insured_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="医保支付金额")
    self_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="自付金额")
    claim_status: Mapped[str] = mapped_column(
        Enum("已结算", "已退回", name="claim_status_enum"),
        nullable=False, default="已结算", comment="结算状态",
    )
    submit_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="结算时间")


# ============================================================
# 药品订单域
# ============================================================

class DrugOrder(Base):
    """药品订单表 (处方流转后的"商品"环节)"""
    __tablename__ = "drug_order"

    drug_order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="药品订单ID")
    rx_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联处方ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="患者用户ID")
    drug_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="药品名称")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="数量")
    drug_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="药品类别")
    is_otc: Mapped[int] = mapped_column(Integer, default=0, comment="是否OTC(1=非处方药)")
    receiver_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人姓名")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="订单金额")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")


# ============================================================
# 扩展黑名单
# ============================================================

class BlacklistExtra(Base):
    """扩展黑名单表 (业务侧: 医保卡/身份证/执业证/医院编码)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    type: Mapped[str] = mapped_column(
        Enum("医保卡", "身份证", "执业证", "医院编码", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="创建时间")