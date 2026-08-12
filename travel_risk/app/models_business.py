"""
旅游风控系统 - 业务表 ORM (18 张)
只读映射旅游业务系统的核心实体 (用户/产品/供应商/旅游订单/出行人/支付/退改/理赔/投诉/点评/设备)
不参与风控决策本身, 但被特征工程和规则引擎查询
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与产品基础
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="注册手机号")
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    register_channel: Mapped[Optional[str]] = mapped_column(String(20), comment="注册渠道")
    is_verified: Mapped[int] = mapped_column(Integer, default=0, comment="是否实名认证")


class Region(Base):
    """目的地区域表"""
    __tablename__ = "region"

    country: Mapped[str] = mapped_column(String(20), primary_key=True, comment="国家")
    province: Mapped[str] = mapped_column(String(20), primary_key=True, comment="省/州")
    city: Mapped[str] = mapped_column(String(20), primary_key=True, comment="城市")


class ProductCategory(Base):
    """产品分类表"""
    __tablename__ = "product_category"

    product_category: Mapped[str] = mapped_column(String(20), primary_key=True, comment="产品分类")


class SupplierInfo(Base):
    """供应商表"""
    __tablename__ = "supplier_info"

    supplier_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="供应商ID")
    supplier_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="供应商名称")
    supplier_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="供应商类型")
    credit_score: Mapped[int] = mapped_column(Integer, default=100, comment="供应商信用分")
    complaint_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计被投诉次数")
    order_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计成交订单数")


class BookingStatus(Base):
    """旅游订单状态表"""
    __tablename__ = "booking_status"

    booking_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="订单状态")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class DeviceInfo(Base):
    """设备表"""
    __tablename__ = "device_info"

    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备ID")
    device_model: Mapped[Optional[str]] = mapped_column(String(100), comment="设备型号")
    os: Mapped[Optional[str]] = mapped_column(String(50), comment="操作系统")
    browser: Mapped[Optional[str]] = mapped_column(String(50), comment="浏览器")


# ============================================================
# 产品与出行人
# ============================================================

class ProductInfo(Base):
    """旅游产品表"""
    __tablename__ = "product_info"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="产品ID")
    product_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    product_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="产品分类")
    supplier_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="供应商ID")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="产品单价")
    destination_country: Mapped[str] = mapped_column(String(20), nullable=False, comment="目的地国家")
    destination_province: Mapped[Optional[str]] = mapped_column(String(20), comment="目的地省/州")
    destination_city: Mapped[Optional[str]] = mapped_column(String(20), comment="目的地城市")
    stock: Mapped[int] = mapped_column(Integer, default=0, comment="库存")
    is_overseas: Mapped[int] = mapped_column(Integer, default=0, comment="是否出境游")
    trip_days: Mapped[int] = mapped_column(Integer, default=1, comment="行程天数")


class TravelerInfo(Base):
    """出行人表"""
    __tablename__ = "traveler_info"

    traveler_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="出行人ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="所属用户ID")
    traveler_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="出行人姓名")
    id_card_no: Mapped[Optional[str]] = mapped_column(String(30), comment="身份证号")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="出行人手机号")


# ============================================================
# 核心交易域
# ============================================================

class BookingInfo(Base):
    """旅游订单表"""
    __tablename__ = "booking_info"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="旅游订单ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")
    departure_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="出发时间")
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="行程结束时间")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="联系人手机号")
    booking_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="订单状态")
    traveler_count: Mapped[int] = mapped_column(Integer, default=1, comment="出行人数")


class CouponInfo(Base):
    """优惠券表"""
    __tablename__ = "coupon_info"

    coupon_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="优惠券ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    coupon_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="优惠金额")
    coupon_status: Mapped[str] = mapped_column(String(20), default="未使用", comment="优惠券状态")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间")


class PaymentInfo(Base):
    """支付记录表"""
    __tablename__ = "payment_info"

    payment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="支付ID")
    booking_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅游订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    pay_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="支付时间")
    pay_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="支付金额")
    pay_channel: Mapped[str] = mapped_column(String(20), nullable=False, comment="支付渠道")
    pay_status: Mapped[str] = mapped_column(String(20), default="成功", comment="支付状态")


class BookingDetail(Base):
    """旅游订单明细表"""
    __tablename__ = "booking_detail"

    booking_detail_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单明细ID")
    booking_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅游订单ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品ID")
    product_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="产品单价")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="总计金额")
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="优惠金额")
    final_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实付金额")


class BookingTraveler(Base):
    """订单出行人关联表"""
    __tablename__ = "booking_traveler"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="旅游订单ID")
    traveler_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="出行人ID")
    relation: Mapped[Optional[str]] = mapped_column(String(20), comment="关系(本人/同行人)")


class UserDevice(Base):
    """用户设备绑定表"""
    __tablename__ = "user_device"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备ID")
    bind_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="绑定时间")


# ============================================================
# 售后与体验域
# ============================================================

class RefundChange(Base):
    """退改申请表"""
    __tablename__ = "refund_change"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退改申请ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")
    booking_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅游订单ID")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="退改金额")
    refund_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="退改类型")
    refund_reason: Mapped[Optional[str]] = mapped_column(String(500), comment="退改原因")
    refund_status: Mapped[str] = mapped_column(String(20), default="处理中", comment="退改状态")


class ComplaintInfo(Base):
    """投诉记录表"""
    __tablename__ = "complaint_info"

    complaint_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="投诉ID")
    booking_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅游订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    complaint_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投诉时间")
    complaint_content: Mapped[str] = mapped_column(String(500), nullable=False, comment="投诉内容")
    complaint_type: Mapped[Optional[str]] = mapped_column(String(50), comment="投诉类型")
    complaint_status: Mapped[str] = mapped_column(String(20), default="处理中", comment="处理状态")


class ClaimInfo(Base):
    """理赔申请表"""
    __tablename__ = "claim_info"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="理赔申请ID")
    booking_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅游订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    claim_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="理赔类型")
    claim_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="理赔金额")
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    claim_status: Mapped[str] = mapped_column(String(20), default="审核中", comment="理赔状态")


class ReviewInfo(Base):
    """点评表"""
    __tablename__ = "review_info"

    review_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="点评ID")
    booking_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅游订单ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    rating: Mapped[int] = mapped_column(SmallInteger, default=5, comment="评分(1-5)")
    content: Mapped[Optional[str]] = mapped_column(Text, comment="点评内容")
    review_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="点评时间")
    is_verified: Mapped[int] = mapped_column(Integer, default=1, comment="是否已购验证")
