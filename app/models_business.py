"""
医疗风控系统 - 业务表 ORM (8 张)
医疗行业业务表, 跟风控表分开管理 (行业重做部分, 电商版 17 张 → 医疗版 8 张)

4 大业务场景: 医保结算 / 处方审核 / 挂号黄牛 / 药品代购

- 患者档案 (UserInfo)         医保卡号 / 参保类型 / 参保地 (医疗特有)
- 医院档案 (Hospital)          医院等级 / 医保定点 (电商没"医院"概念)
- 医生档案 (Doctor)            科室 / 职称 / 执业证号 (电商没"医生")
- 挂号记录 (Appointment)       电商"订单"变"挂号"
- 处方单 (Prescription)        电商没"处方", 含诊断编码 + 药品明细
- 医保结算 (InsuranceClaim)    强监管, 跟电商"支付"完全不同
- 药品订单 (DrugOrder)         处方流转后的"商品"环节, 含收件人
- 行业黑名单 (BlacklistExtra)  医保卡号 / 身份证号 / 医生执业证 / 医院编码
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
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
# 患者档案
# ============================================================

class UserInfo(Base):
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="患者ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    id_card_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="身份证号哈希(SHA256, 脱敏存储)")
    medical_card_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="医保卡号")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="手机号")
    insurance_type: Mapped[str] = mapped_column(
        Enum("职工医保", "居民医保", "新农合", "自费", name="insurance_type_enum"),
        nullable=False, default="居民医保", comment="参保类型",
    )
    insured_province: Mapped[Optional[str]] = mapped_column(String(50), comment="参保地省份")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="建档时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_user_medical_card", "medical_card_no"),
        Index("idx_user_id_card_hash", "id_card_hash"),
    )


# ============================================================
# 医院档案
# ============================================================

class Hospital(Base):
    __tablename__ = "hospital"

    hospital_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="医院编码")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="医院名称")
    level: Mapped[str] = mapped_column(
        Enum("三甲", "三乙", "二甲", "二乙", "社区", name="hospital_level_enum"),
        nullable=False, default="二甲", comment="医院等级",
    )
    province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省份")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="城市")
    is_insured: Mapped[int] = mapped_column(Integer, default=1, comment="是否医保定点(1=是,0=否)")


# ============================================================
# 医生档案
# ============================================================

class Doctor(Base):
    __tablename__ = "doctor"

    doctor_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="医生ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="所属医院编码")
    department: Mapped[str] = mapped_column(String(50), nullable=False, comment="科室")
    title: Mapped[str] = mapped_column(
        Enum("主任医师", "副主任医师", "主治医师", "住院医师", name="doctor_title_enum"),
        nullable=False, default="主治医师", comment="职称",
    )
    license_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="执业证号")

    __table_args__ = (
        Index("idx_doctor_hospital", "hospital_id"),
    )


# ============================================================
# 挂号记录 (电商"订单" → 医疗"挂号")
# ============================================================

class Appointment(Base):
    __tablename__ = "appointment"

    appt_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="挂号ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="患者ID")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="医院编码")
    department: Mapped[str] = mapped_column(String(50), nullable=False, comment="挂号科室")
    doctor_id: Mapped[Optional[str]] = mapped_column(String(50), comment="医生ID")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="预约手机号(黄牛识别用)")
    appt_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="预约就诊时间")
    pay_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="挂号费")
    appt_status: Mapped[str] = mapped_column(
        Enum("已预约", "已就诊", "已取消", name="appt_status_enum"),
        nullable=False, default="已预约", comment="挂号状态",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_appt_user_id", "user_id"),
        Index("idx_appt_hospital_id", "hospital_id"),
        Index("idx_appt_phone", "phone"),
        Index("idx_appt_create_time", "create_time"),
    )


# ============================================================
# 处方单 (处方审核场景核心)
# ============================================================

class Prescription(Base):
    __tablename__ = "prescription"

    rx_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="处方ID")
    doctor_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="开方医生ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="患者ID")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="医院编码")
    diagnosis_code: Mapped[Optional[str]] = mapped_column(String(20), comment="诊断编码(ICD-10)")
    items: Mapped[Optional[str]] = mapped_column(
        Text, comment='药品明细 JSON, 如 [{"drug": "阿普唑仑片", "quantity": 20}]',
    )
    item_count: Mapped[int] = mapped_column(Integer, default=1, comment="处方药品行数")
    total_quantity: Mapped[int] = mapped_column(Integer, default=0, comment="药品总数量(片/盒)")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="处方总金额")
    is_insured: Mapped[int] = mapped_column(Integer, default=1, comment="是否医保处方(1=是,0=否)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="开方时间",
    )

    __table_args__ = (
        Index("idx_rx_user_id", "user_id"),
        Index("idx_rx_doctor_id", "doctor_id"),
        Index("idx_rx_create_time", "create_time"),
    )


# ============================================================
# 医保结算 (强监管, 医保结算场景核心)
# ============================================================

class InsuranceClaim(Base):
    __tablename__ = "insurance_claim"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="结算单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="患者ID")
    hospital_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="结算医院编码")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="医疗总费用")
    insured_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="医保报销金额")
    claim_status: Mapped[str] = mapped_column(
        Enum("待审核", "已结算", "已拒绝", name="claim_status_enum"),
        nullable=False, default="待审核", comment="结算状态",
    )
    submit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="提交结算时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_claim_user_id", "user_id"),
        Index("idx_claim_hospital_id", "hospital_id"),
        Index("idx_claim_submit_at", "submit_at"),
    )


# ============================================================
# 药品订单 (处方流转后的"商品"环节, 药品代购场景核心)
# ============================================================

class DrugOrder(Base):
    __tablename__ = "drug_order"

    drug_order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="药品订单ID")
    rx_id: Mapped[Optional[str]] = mapped_column(String(50), comment="关联处方ID(OTC 可为空)")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="下单患者ID")
    drug_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="药品名称")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="购买数量")
    drug_category: Mapped[str] = mapped_column(
        Enum("处方药", "OTC", "麻醉药品", "精神药品", name="drug_category_enum"),
        nullable=False, default="处方药", comment="药品类别",
    )
    is_otc: Mapped[int] = mapped_column(Integer, default=0, comment="是否 OTC(1=是,0=否)")
    receiver_name: Mapped[Optional[str]] = mapped_column(String(50), comment="收件人姓名(代购识别: !=患者本人)")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="订单金额")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="下单时间",
    )

    __table_args__ = (
        Index("idx_drug_order_user_id", "user_id"),
        Index("idx_drug_order_rx_id", "rx_id"),
        Index("idx_drug_order_create_time", "create_time"),
    )


# ============================================================
# 行业黑名单登记 (业务侧登记簿, 风控撞黑走 risk_blacklist)
# ============================================================

class BlacklistExtra(Base):
    """
    行业黑名单登记表.
    type 为医疗行业专属 4 类: 医保卡号 / 身份证号 / 医生执业证 / 医院编码.
    数据初始化时同步一份到 risk_blacklist, 风控引擎撞黑检查走 risk_blacklist.
    """
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="登记ID")
    type: Mapped[str] = mapped_column(
        Enum("医保卡号", "身份证号", "医生执业证", "医院编码", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="登记原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="失效时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="登记时间",
    )
