"""
物流风控系统 - 业务表 ORM (8 张)
映射物流行业核心实体: 用户 / 地址 / 物品分类 / 运单状态 / 运单 / 运单物品明细 / 跨境申报 / 投诉
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与基础维度
# ============================================================

class UserInfo(Base):
    """用户信息表 (寄件人 / 收件人 统一用 user 区分 role)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    user_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户姓名")
    user_role: Mapped[str] = mapped_column(
        Enum("寄件人", "收件人", "两者都是", name="user_role_enum"),
        nullable=False, default="两者都是", comment="用户角色",
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(100), comment="身份证号哈希")
    real_name_status: Mapped[str] = mapped_column(
        Enum("未实名", "已实名", "实名中", "实名失败", name="real_name_status_enum"),
        nullable=False, default="未实名", comment="实名认证状态",
    )
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="注册时间")
    vip_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="VIP等级 0-5")
    total_shipments: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计寄件次数")


class Address(Base):
    """地址表 (收/寄件地址)"""
    __tablename__ = "address"

    address_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="地址ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="关联用户ID")
    address_tag: Mapped[str] = mapped_column(
        Enum("家", "公司", "学校", "朋友", "代收点", "其他", name="address_tag_enum"),
        nullable=False, default="家", comment="地址标签",
    )
    contact_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="联系人姓名")
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="联系人电话")
    province: Mapped[str] = mapped_column(String(20), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(20), nullable=False, comment="市")
    district: Mapped[str] = mapped_column(String(20), nullable=False, comment="区")
    street_address: Mapped[str] = mapped_column(String(200), nullable=False, comment="详细街道地址")
    is_remote: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否偏远地区 0否1是")
    is_temporary: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否临时地址 0否1是")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")


class ItemCategory(Base):
    """物品分类表 (物流禁运/危险品分类)"""
    __tablename__ = "item_category"

    category_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment="物品分类编码")
    category_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="分类名称")
    is_dangerous: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否危险品 0否1是")
    is_prohibited: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否禁运品 0否1是")
    need_real_name: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否需要实名 0否1是")
    description: Mapped[Optional[str]] = mapped_column(String(200), comment="分类说明")


# ============================================================
# 运单核心
# ============================================================

class ShipmentStatus(Base):
    """运单状态表"""
    __tablename__ = "shipment_status"

    status_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment="状态编码")
    status_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="状态名称")
    description: Mapped[Optional[str]] = mapped_column(String(200), comment="状态说明")


class Shipment(Base):
    """运单主表"""
    __tablename__ = "shipment"

    shipment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="运单ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment="运单号")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    pick_up_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="揽收时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    sender_user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="寄件人用户ID")
    receiver_user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="收件人用户ID")
    sender_address_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("address.address_id"), nullable=False, comment="寄件地址ID")
    receiver_address_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("address.address_id"), nullable=False, comment="收件地址ID")
    shipment_type: Mapped[str] = mapped_column(
        Enum("普通标快", "生鲜冷链", "次日达", "隔日达", "国际快递", name="shipment_type_enum"),
        nullable=False, default="普通标快", comment="运输类型",
    )
    payment_method: Mapped[str] = mapped_column(
        Enum("寄付现结", "到付", "月结", "寄付月结", name="payment_method_enum"),
        nullable=False, default="寄付现结", comment="付款方式",
    )
    total_weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=0, comment="总重量(kg)")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="申报价值(元)")
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="运费金额")
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="代收货款金额")
    insurance_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="保价金额")
    shipment_status: Mapped[str] = mapped_column(String(20), ForeignKey("shipment_status.status_code"), nullable=False, default="CREATED", comment="运单状态")
    is_cross_border: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否跨境 0否1是")
    reject_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="拒收次数")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="物品件数")


class ShipmentItem(Base):
    """运单物品明细表"""
    __tablename__ = "shipment_item"

    item_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物品明细ID")
    shipment_id: Mapped[str] = mapped_column(String(50), ForeignKey("shipment.shipment_id"), nullable=False, comment="运单ID")
    item_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="物品名称")
    category_code: Mapped[str] = mapped_column(String(20), ForeignKey("item_category.category_code"), nullable=False, comment="物品分类编码")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="数量")
    unit_weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=0, comment="单件重量(kg)")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="申报价值")
    is_dangerous_declared: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="申报是否危险品 0否1是")
    hs_code: Mapped[Optional[str]] = mapped_column(String(20), comment="HS编码(跨境用)")


# ============================================================
# 跨境与投诉
# ============================================================

class CustomsDeclaration(Base):
    """跨境申报记录表"""
    __tablename__ = "customs_declaration"

    declaration_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="申报ID")
    shipment_id: Mapped[str] = mapped_column(String(50), ForeignKey("shipment.shipment_id"), nullable=False, comment="关联运单ID")
    declare_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="申报时间")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的国家")
    dest_customs_code: Mapped[Optional[str]] = mapped_column(String(50), comment="目的国海关编码")
    sender_id_card: Mapped[Optional[str]] = mapped_column(String(50), comment="寄件人证件号")
    receiver_id_card: Mapped[Optional[str]] = mapped_column(String(50), comment="收件人证件号")
    total_declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="申报总价值")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CNY", comment="币种")
    declare_status: Mapped[str] = mapped_column(
        Enum("待申报", "已申报", "审核中", "已放行", "被扣留", name="declare_status_enum"),
        nullable=False, default="待申报", comment="申报状态",
    )
    is_value_mismatch: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="申报价值是否异常 0否1是")


class ComplaintRecord(Base):
    """物流投诉记录表"""
    __tablename__ = "complaint_record"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="投诉记录ID")
    shipment_id: Mapped[str] = mapped_column(String(50), ForeignKey("shipment.shipment_id"), nullable=False, comment="关联运单ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"), nullable=False, comment="投诉用户ID")
    complaint_type: Mapped[str] = mapped_column(
        Enum("延误", "破损", "丢失", "服务态度差", "费用争议", "派送失败", "虚假签收", name="complaint_type_enum"),
        nullable=False, default="延误", comment="投诉类型",
    )
    complaint_content: Mapped[str] = mapped_column(Text, nullable=False, comment="投诉内容")
    complaint_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="投诉时间")
    claim_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="索赔金额")
    handle_status: Mapped[str] = mapped_column(
        Enum("待处理", "处理中", "已结案", "已驳回", name="handle_status_enum"),
        nullable=False, default="待处理", comment="处理状态",
    )
    is_malicious: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否恶意投诉 0否1是")
