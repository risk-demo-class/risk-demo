"""物流风控系统业务表 ORM。

业务层仅包含寄递用户、地址、运单、物品明细和扩展黑名单 5 张表。
风控核心仍把运单/地址称为 order/receive，因此在文件末尾提供只供核心引擎
使用的兼容别名；数据库中不会创建任何电商表。
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.database import Base


class UserInfo(Base):
    """寄递用户（寄件人、收件人或兼具两种角色）。"""

    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    user_role: Mapped[str] = mapped_column(
        Enum("寄件人", "收件人", "双方", name="logistics_user_role_enum"),
        default="寄件人", nullable=False, comment="寄递角色",
    )
    full_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, comment="联系电话")
    id_type: Mapped[str] = mapped_column(String(30), default="居民身份证", comment="证件类型")
    id_no_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="证件号SHA-256")
    id_no_masked: Mapped[str] = mapped_column(String(32), nullable=False, comment="证件号掩码")
    real_name_status: Mapped[str] = mapped_column(
        Enum("已核验", "未核验", "信息不符", "证件过期", name="real_name_status_enum"),
        default="已核验", nullable=False, comment="实名核验状态",
    )
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(100), comment="设备指纹")
    last_ip: Mapped[Optional[str]] = mapped_column(String(64), comment="最近IP")
    account_status: Mapped[str] = mapped_column(
        Enum("正常", "限制寄件", "停用", name="logistics_account_status_enum"),
        default="正常", nullable=False, comment="账户状态",
    )
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_user_phone", "phone"),
        Index("idx_user_id_hash", "id_no_hash"),
        Index("idx_user_device", "device_fingerprint"),
        Index("idx_user_last_ip", "last_ip"),
    )


class Address(Base):
    """寄递地址，保存标准化哈希和临时/偏远标识。"""

    __tablename__ = "address"

    address_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="地址ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="地址所属用户ID")
    contact_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="联系人")
    contact_phone: Mapped[str] = mapped_column(String(32), nullable=False, comment="联系电话")
    province: Mapped[str] = mapped_column(String(30), nullable=False)
    city: Mapped[str] = mapped_column(String(30), nullable=False)
    district: Mapped[str] = mapped_column(String(30), nullable=False)
    detail_address: Mapped[str] = mapped_column(String(200), nullable=False, comment="详细地址")
    normalized_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化地址哈希")
    address_type: Mapped[str] = mapped_column(
        Enum("住宅", "单位", "驿站", "临时", name="address_type_enum"),
        default="住宅", nullable=False,
    )
    is_remote: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="是否偏远")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    # 核心引擎兼容字段（SQLAlchemy synonym，不创建额外列）
    receive_id = synonym("address_id")
    receiver_name = synonym("contact_name")
    receiver_phone = synonym("contact_phone")
    receive_province = synonym("province")
    receive_city = synonym("city")
    receive_district = synonym("district")
    receive_street_address = synonym("detail_address")

    __table_args__ = (
        Index("idx_address_user", "user_id"),
        Index("idx_address_hash", "normalized_hash"),
        Index("idx_address_region", "province", "city", "district"),
    )


class Shipment(Base):
    """物流运单主表。"""

    __tablename__ = "shipment"

    shipment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="运单ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment="运单号")
    sender_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄件人ID")
    receiver_id: Mapped[Optional[str]] = mapped_column(String(50), comment="收件人用户ID")
    sender_address_id: Mapped[Optional[str]] = mapped_column(String(50), comment="寄件地址ID")
    receiver_address_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件地址ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    pickup_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="揽收时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    shipment_status: Mapped[str] = mapped_column(
        Enum("待揽收", "运输中", "已签收", "拒收退回", "已取消", "海关查验", "安全拦截",
             name="shipment_status_enum"),
        default="待揽收", nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        Enum("柜台", "上门取件", "直营网点", "合作平台", name="shipment_channel_enum"),
        default="上门取件", nullable=False,
    )
    payment_type: Mapped[str] = mapped_column(
        Enum("寄付", "到付", "代收货款", name="shipment_payment_type_enum"),
        default="寄付", nullable=False,
    )
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    cod_status: Mapped[str] = mapped_column(
        Enum("无", "待收", "已收", "拒收", "退回", name="cod_status_enum"),
        default="无", nullable=False,
    )
    is_cross_border: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    origin_country: Mapped[str] = mapped_column(String(50), default="中国", nullable=False)
    destination_country: Mapped[str] = mapped_column(String(50), default="中国", nullable=False)
    customs_subject: Mapped[Optional[str]] = mapped_column(String(100), comment="海关申报主体")
    customs_status: Mapped[str] = mapped_column(
        Enum("不适用", "待申报", "已放行", "查验中", "退运", name="customs_status_enum"),
        default="不适用", nullable=False,
    )
    declared_weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    actual_weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    customs_assessed_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    real_name_verified: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    inspection_status: Mapped[str] = mapped_column(
        Enum("待验视", "已通过", "疑似危险品", "拒绝收寄", name="inspection_status_enum"),
        default="待验视", nullable=False,
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="教学样本标签")
    risk_pattern: Mapped[Optional[str]] = mapped_column(String(100), comment="教学风险模式")

    # 未改动的 decision.py 只认识订单字段；这些均为 ORM 别名，不产生电商列。
    order_id = synonym("shipment_id")
    user_id = synonym("sender_id")
    receive_id = synonym("receiver_address_id")
    order_status = synonym("shipment_status")

    __table_args__ = (
        Index("idx_shipment_sender_time", "sender_id", "create_time"),
        Index("idx_shipment_receiver_address", "receiver_address_id"),
        Index("idx_shipment_cross_border", "is_cross_border", "customs_status"),
        Index("idx_shipment_cod", "payment_type", "cod_status"),
        Index("idx_shipment_risk_label", "risk_label"),
    )


class ShipmentItem(Base):
    """运单物品明细和验视结果。"""

    __tablename__ = "shipment_item"

    item_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    declared_category: Mapped[str] = mapped_column(String(50), nullable=False)
    actual_category: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    dangerous_declared: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detected_dangerous_type: Mapped[Optional[str]] = mapped_column(String(50))
    inspection_result: Mapped[str] = mapped_column(
        Enum("正常", "限寄", "禁寄", "信息不符", name="item_inspection_result_enum"),
        default="正常", nullable=False,
    )

    __table_args__ = (
        Index("idx_shipment_item_shipment", "shipment_id"),
        Index("idx_shipment_item_danger", "inspection_result", "dangerous_declared"),
    )


class BlacklistExtra(Base):
    """不适合放入核心三类黑名单的物流业务实体。"""

    __tablename__ = "blacklist_extra"

    extra_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(
        Enum("实名证件", "设备指纹", "IP地址", "海关主体", name="blacklist_extra_type_enum"),
        nullable=False,
    )
    entity_value: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="人工录入", nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("启用", "停用", name="blacklist_extra_status_enum"), default="启用", nullable=False,
    )
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_value", name="uq_blacklist_extra_type_value"),
        Index("idx_blacklist_extra_status", "status", "expire_time"),
    )


# 核心引擎兼容别名。仅 Python import 可见，数据库仍只有 shipment/address。
OrderInfo = Shipment
ReceiveInfo = Address

