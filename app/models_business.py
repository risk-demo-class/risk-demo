"""
物流风控系统 - 业务表 ORM (7 张核心表 + 2 张支撑表)

覆盖 4 大物流场景: 寄递实名 / 危险品申报 / 跨境包裹 / 代收货款(COD).
业务核心是"物"(包裹/重量/品类), 不是电商的"钱"(订单金额/支付).

与电商版的差异:
  - 电商"订单" → 物流"包裹" (Parcel), 寄收双方都是风控对象
  - 新增物流专属表: DangerousDeclaration(危险品申报) / CodTransaction(代收货款流水)
  - 新增物流业务黑名单表: BlacklistExtra (身份证/手机号/地址/面单条码/IP)
  - 寄件人 SenderInfo 承载实名认证, 收件人 ReceiverInfo 标记是否代签收

约定: sender_id 与 user_id 一致 (寄件人账号即风控主体 user_id), 简化特征查询.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 基础维度表
# ============================================================

class Region(Base):
    """省份编码表: 省份名称 → 省份编码 (特征计算用, 支持"跨省/省份编码"特征)."""
    __tablename__ = "region"

    province: Mapped[str] = mapped_column(String(20), primary_key=True, comment="省份名称")
    province_code: Mapped[int] = mapped_column(Integer, nullable=False, comment="省份编码")


class ItemCategory(Base):
    """物品类目表: 包裹 item_category 的可选值 (电子产品/服装/食品/化工品/普通)."""
    __tablename__ = "item_category"

    item_category: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物品类目")


# ============================================================
# 用户与实名域
# ============================================================

class UserInfo(Base):
    """寄件用户信息表: 区分个人/企业寄件人 (account_type)."""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID(寄件人账号)")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    real_name_status: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="实名状态(已认证/未认证/认证失败)",
    )
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="账号类型(personal个人/enterprise企业)",
    )
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class SenderInfo(Base):
    """寄件人实名表: 物流风控双向对象之一 (寄件人)."""
    __tablename__ = "sender_info"

    sender_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="寄件人ID(与 user_id 一致)")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    id_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="证件类型(身份证/护照/军官证)")
    id_number: Mapped[str] = mapped_column(String(50), nullable=False, comment="证件号码")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    address: Mapped[str] = mapped_column(String(200), nullable=False, comment="寄件地址")
    sender_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="寄件省份")
    is_blacklisted: Mapped[int] = mapped_column(Integer, default=0, comment="是否黑名单(0/1)")


class ReceiverInfo(Base):
    """收件人表: 1 包裹 1 收件人; is_proxy_received 标记是否代签收."""
    __tablename__ = "receiver_info"

    receiver_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="收件人ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    address: Mapped[str] = mapped_column(String(200), nullable=False, comment="收件地址")
    receiver_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件省份")
    is_proxy_received: Mapped[int] = mapped_column(Integer, default=0, comment="是否代签收(0/1)")


# ============================================================
# 包裹域 (核心业务表)
# ============================================================

class Parcel(Base):
    """包裹表: 物流风控的核心实体, 电商"订单" → 物流"包裹", 业务核心是"物"不是"钱"."""
    __tablename__ = "parcel"

    parcel_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="包裹ID(面单号)")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄件用户ID(风控主体)")
    sender_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="寄件人ID")
    receiver_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="收件人ID")
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, comment="实际称重(kg)")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="申报价值(元)")
    item_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="物品类目(电子产品/服装/食品/化工品/普通)")
    is_international: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否国际件(0/1)")
    piece_count: Mapped[Optional[int]] = mapped_column(Integer, comment="货物件数(用于大额低报规则)")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created",
        comment="状态(created/in_transit/delivered/returned)",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="揽收时间")


class DangerousDeclaration(Base):
    """危险品申报表 (物流专属): 寄递物品的危险品申报与检测."""
    __tablename__ = "dangerous_declaration"

    decl_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="申报ID")
    parcel_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="包裹ID")
    item_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="物品类型(锂电池/液体/粉末等)")
    is_liquid: Mapped[int] = mapped_column(Integer, default=0, comment="是否液体(0/1)")
    is_battery: Mapped[int] = mapped_column(Integer, default=0, comment="是否含电池(0/1)")
    msds_url: Mapped[Optional[str]] = mapped_column(String(200), comment="MSDS 安全数据表链接")
    declared_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申报时间")


class CodTransaction(Base):
    """代收货款流水表 (物流专属): 货到付款(COD)场景的资金流转, 跟电商"已付款"完全不同."""
    __tablename__ = "cod_transaction"

    cod_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="COD ID")
    parcel_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="包裹ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="代收金额(元)")
    cod_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="状态(pending待收/paid已付/returned已退/overdue逾期)",
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="实际付款时间")
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="退回时间")
    days_overdue: Mapped[Optional[int]] = mapped_column(Integer, comment="逾期天数(签收后未付款)")


class BlacklistExtra(Base):
    """物流业务黑名单扩展表: type 加 身份证号/手机号/地址/面单条码 (电商只有用户/地址/手机号)."""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单条目ID")
    type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="黑名单类型(id_number身份证号/phone手机号/address地址/waybill_barcode面单条码/ip_address IP)",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
