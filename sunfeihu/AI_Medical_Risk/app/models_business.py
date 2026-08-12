"""
医疗风控系统 - 医疗业务表 ORM (P0 新建, 8 张)
字段/约束严格对齐 PRD §7.1 / §7.3 / §7.4:
- 所有敏感标识只保存合成值或不可逆摘要 (hash), 不保存真实个人信息
- 时间字段统一到秒 (DATETIME); 金额统一 DECIMAL, 禁止浮点
- 外键字段建普通索引; 高频统计建组合索引
- id_card_hash / insurance_card_hash / phone_hash 唯一

ORM 与 sql/init_business_tables.sql 必须保持一致 (见 tests/test_ddl_consistency.py).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 1. 患者主档
# ============================================================

class MedicalPatient(Base):
    __tablename__ = "medical_patient"

    patient_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="患者ID")
    name_masked: Mapped[str] = mapped_column(String(50), nullable=False, comment="脱敏姓名(合成)")
    id_card_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="身份证摘要(SHA-256,合成)")
    insurance_card_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="医保卡摘要(SHA-256,合成)")
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="手机号摘要(SHA-256,合成)")
    gender: Mapped[str] = mapped_column(
        Enum("男", "女", "未知", name="patient_gender_enum"),
        nullable=False, server_default="未知", comment="性别",
    )
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False, comment="出生年份")
    insured_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="参保省份")
    account_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="账户创建时间")
    real_name_status: Mapped[str] = mapped_column(
        Enum("已实名", "未实名", name="patient_real_name_enum"),
        nullable=False, server_default="已实名", comment="实名状态",
    )

    __table_args__ = (
        UniqueConstraint("id_card_hash", name="uniq_patient_id_card_hash"),
        UniqueConstraint("insurance_card_hash", name="uniq_patient_ins_card_hash"),
        UniqueConstraint("phone_hash", name="uniq_patient_phone_hash"),
        Index("idx_patient_province", "insured_province"),
    )


# ============================================================
# 2. 医疗机构档案
# ============================================================

class MedicalHospital(Base):
    __tablename__ = "medical_hospital"

    hospital_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="医疗机构ID")
    hospital_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="机构名称(合成)")
    province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省份")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="城市")
    hospital_level: Mapped[str] = mapped_column(
        Enum("三级", "二级", "一级", "未定级", name="hospital_level_enum"),
        nullable=False, server_default="三级", comment="医院等级",
    )
    hospital_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="机构类型(综合医院/专科/中医...)")
    insurance_designated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", comment="是否医保定点")
    status: Mapped[str] = mapped_column(
        Enum("正常", "异常", "停用", name="hospital_status_enum"),
        nullable=False, server_default="正常", comment="机构状态",
    )

    __table_args__ = (
        Index("idx_hospital_province", "province"),
        Index("idx_hospital_status", "status"),
    )


# ============================================================
# 3. 医生档案
# ============================================================

class MedicalDoctor(Base):
    __tablename__ = "medical_doctor"

    doctor_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="医生ID")
    doctor_name_masked: Mapped[str] = mapped_column(String(50), nullable=False, comment="脱敏姓名(合成)")
    hospital_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_hospital.hospital_id"), nullable=False, comment="所属医院ID",
    )
    department: Mapped[str] = mapped_column(String(50), nullable=False, comment="科室")
    professional_title: Mapped[str] = mapped_column(String(50), nullable=False, comment="职称")
    license_status: Mapped[str] = mapped_column(
        Enum("有效", "异常", "注销", "暂停", name="doctor_license_enum"),
        nullable=False, server_default="有效", comment="执业状态(异常时触发 MR014)",
    )
    practice_start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="执业起始日期")
    status: Mapped[str] = mapped_column(
        Enum("在职", "离职", "异常", name="doctor_status_enum"),
        nullable=False, server_default="在职", comment="医生状态",
    )

    __table_args__ = (
        Index("idx_doctor_hospital", "hospital_id"),
        Index("idx_doctor_department", "department"),
        Index("idx_doctor_license", "license_status"),
    )


# ============================================================
# 4. 挂号记录
# ============================================================

class MedicalRegistration(Base):
    __tablename__ = "medical_registration"

    registration_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="挂号ID")
    patient_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_patient.patient_id"), nullable=False, comment="患者ID",
    )
    hospital_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_hospital.hospital_id"), nullable=False, comment="医院ID",
    )
    doctor_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_doctor.doctor_id"), nullable=False, comment="医生ID",
    )
    department: Mapped[str] = mapped_column(String(50), nullable=False, comment="科室")
    visit_date: Mapped[date] = mapped_column(Date, nullable=False, comment="就诊日期")
    register_channel: Mapped[str] = mapped_column(
        Enum("窗口", "微信", "APP", "自助机", "电话", name="register_channel_enum"),
        nullable=False, server_default="微信", comment="挂号渠道",
    )
    device_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="设备指纹摘要")
    status: Mapped[str] = mapped_column(
        Enum("已挂号", "已退号", "已完成", name="registration_status_enum"),
        nullable=False, server_default="已挂号", comment="挂号状态",
    )
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="挂号时间")
    cancel_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="退号时间(NULL=未退号)")

    __table_args__ = (
        # 外键普通索引 (PRD §7.4)
        Index("idx_reg_patient", "patient_id"),
        Index("idx_reg_hospital", "hospital_id"),
        Index("idx_reg_doctor", "doctor_id"),
        # 高频过滤 / 统计
        Index("idx_reg_status", "status"),
        Index("idx_reg_device", "device_id_hash"),
        Index("idx_reg_register_at", "register_at"),
    )


# ============================================================
# 5. 处方主表
# ============================================================

class MedicalPrescription(Base):
    __tablename__ = "medical_prescription"

    prescription_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="处方ID")
    patient_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_patient.patient_id"), nullable=False, comment="患者ID",
    )
    doctor_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_doctor.doctor_id"), nullable=False, comment="医生ID",
    )
    hospital_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_hospital.hospital_id"), nullable=False, comment="医院ID",
    )
    registration_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("medical_registration.registration_id"),
        nullable=True, comment="关联挂号ID(可空)",
    )
    prescription_type: Mapped[str] = mapped_column(
        Enum("门诊", "急诊", "住院", name="prescription_type_enum"),
        nullable=False, server_default="门诊", comment="处方类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="处方总金额(DECIMAL)")
    drug_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="药品种数")
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开方时间")
    status: Mapped[str] = mapped_column(
        Enum("有效", "作废", name="prescription_status_enum"),
        nullable=False, server_default="有效", comment="处方状态",
    )

    __table_args__ = (
        Index("idx_rx_patient", "patient_id"),
        Index("idx_rx_doctor", "doctor_id"),
        Index("idx_rx_hospital", "hospital_id"),
        Index("idx_rx_registration", "registration_id"),
        # 组合索引 (PRD §7.4)
        Index("idx_rx_patient_issued", "patient_id", "issued_at"),
        Index("idx_rx_doctor_issued", "doctor_id", "issued_at"),
        Index("idx_rx_status", "status"),
    )


# ============================================================
# 6. 处方药品明细
# ============================================================

class MedicalPrescriptionItem(Base):
    __tablename__ = "medical_prescription_item"

    item_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="明细ID")
    prescription_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_prescription.prescription_id"), nullable=False, comment="处方ID",
    )
    drug_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="药品编码(合成)")
    drug_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="药品名称(合成)")
    drug_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="药品分类(同类药归并)")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="单价(DECIMAL)")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="数量")
    days_supply: Mapped[int] = mapped_column(Integer, nullable=False, comment="供药天数")
    is_controlled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", comment="是否特殊管理药品")
    is_high_value: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", comment="是否高价药")

    __table_args__ = (
        Index("idx_rx_item_prescription", "prescription_id"),
        Index("idx_rx_item_category", "drug_category"),
        Index("idx_rx_item_controlled", "is_controlled"),
    )


# ============================================================
# 7. 医保结算记录
# ============================================================

class MedicalInsuranceClaim(Base):
    __tablename__ = "medical_insurance_claim"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="结算ID")
    patient_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_patient.patient_id"), nullable=False, comment="患者ID",
    )
    hospital_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_hospital.hospital_id"), nullable=False, comment="医院ID",
    )
    prescription_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("medical_prescription.prescription_id"),
        nullable=True, comment="关联处方ID(可空)",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="结算总额(DECIMAL)")
    insurance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="医保支付金额(DECIMAL)")
    self_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="自费金额(DECIMAL)")
    claim_type: Mapped[str] = mapped_column(
        Enum("门诊", "住院", "异地就医", "大病", name="claim_type_enum"),
        nullable=False, server_default="门诊", comment="结算类型",
    )
    visit_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="就医省份")
    claim_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="结算时间")
    status: Mapped[str] = mapped_column(
        Enum("已申报", "已结算", "已拒付", name="claim_status_enum"),
        nullable=False, server_default="已结算", comment="结算状态",
    )

    __table_args__ = (
        Index("idx_claim_patient", "patient_id"),
        Index("idx_claim_hospital", "hospital_id"),
        Index("idx_claim_prescription", "prescription_id"),
        # 组合索引 (PRD §7.4)
        Index("idx_claim_patient_at", "patient_id", "claim_at"),
        Index("idx_claim_hospital_at", "hospital_id", "claim_at"),
        Index("idx_claim_status", "status"),
    )


# ============================================================
# 8. 患者设备关联
# ============================================================

class MedicalPatientDevice(Base):
    __tablename__ = "medical_patient_device"

    relation_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="关联ID")
    patient_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("medical_patient.patient_id"), nullable=False, comment="患者ID",
    )
    device_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="设备指纹摘要")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现时间")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近出现时间")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="使用次数")

    __table_args__ = (
        Index("idx_device_patient", "patient_id"),
        # 同一设备关联多名患者 (MR012 设备关联多患者) 的探查
        Index("idx_device_hash", "device_id_hash"),
        UniqueConstraint("patient_id", "device_id_hash", name="uniq_patient_device"),
    )
