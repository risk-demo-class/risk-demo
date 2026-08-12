"""
物流行业风控系统 - 业务表 ORM
设计符合物流行业特点的模型: 运单、寄件人、收件人、地址、物品明细等
(与 sql/init_logistics_tables.sql 保持一致)
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与地址
# ============================================================

class UserInfo(Base):
    """物流用户信息表 (寄件人 / 收件人)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="真实姓名")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号码")
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="身份证脱敏哈希")
    real_name_verified: Mapped[bool] = mapped_column(Boolean, default=False, comment="实名核验状态")
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, comment="账号年龄(天)")


class Address(Base):
    """地址库"""
    __tablename__ = "address"

    address_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="地址ID")
    province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="市")
    district: Mapped[str] = mapped_column(String(50), nullable=False, comment="区")
    detail: Mapped[str] = mapped_column(String(200), nullable=False, comment="详细地址")
    is_temporary: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否临时地址")


# ============================================================
# 运单
# ============================================================

class Shipment(Base):
    """运单主表"""
    __tablename__ = "shipment"

    shipment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="运单号")
    sender_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄件人ID")
    receiver_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人姓名")
    receiver_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件人手机")

    shipment_type: Mapped[str] = mapped_column(
        Enum("普通", "特快", "跨境", "代收货款", name="shipment_type_enum"),
        nullable=False,
        comment="运单类型",
    )

    declared_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="申报价值")
    actual_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实际重量(kg)")
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="代收货款金额")

    origin_address_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="起始地址ID")
    dest_address_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地址ID")

    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    status: Mapped[str] = mapped_column(String(20), default="待揽收", comment="运单状态")


class ShipmentItem(Base):
    """运单物品明细"""
    __tablename__ = "shipment_item"

    item_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物品ID")
    shipment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    item_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="物品名称")
    item_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="物品分类")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    is_dangerous: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否标识为危险品")


# ============================================================
# 物流状态与投诉
# ============================================================

class LogisticsStatusUpdate(Base):
    """物流状态更新日志"""
    __tablename__ = "logistics_status_update"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="更新ID")
    shipment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    status: Mapped[str] = mapped_column(String(50), nullable=False, comment="状态")
    location: Mapped[str] = mapped_column(String(200), comment="当前位置")
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="更新时间")


class ShipmentComplaint(Base):
    """运单投诉记录"""
    __tablename__ = "shipment_complaint"

    complaint_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="投诉ID")
    shipment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="投诉人ID")
    complaint_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="投诉类型")
    content: Mapped[str] = mapped_column(String(500), comment="投诉内容")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="投诉时间")
