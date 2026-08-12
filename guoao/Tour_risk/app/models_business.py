"""
物流风控系统 - 业务表 ORM (5 张)

物流行业业务边界: 寄递实名 / 危险品 / 跨境 / 代收货款 (COD).
跟电商版的差异: 没有"商品订单/售后", 核心实体是"运单", 收件人用 Address 表,
物品明细用 ShipmentItem 表, 扩展黑名单用 BlacklistExtra 表.

表清单:
  - UserInfo        寄件人 / 收件人档案 (含实名信息)
  - Address         收件地址 (一个人可以挂多个收件地址)
  - Shipment        运单主表 (1 单 = 1 次寄递)
  - ShipmentItem    运单物品明细 (1 单 N 个物品)
  - BlacklistExtra  物流行业扩展黑名单 (身份证号 / 寄件网点)
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
# 用户档案 (寄件人 / 收件人)
# ============================================================

class UserInfo(Base):
    """寄件人/收件人用户表: 实名状态是物流风控的第一道门"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    user_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    # 证件号存哈希, 教学项目直接存明文即可 (生产必须脱敏/加盐哈希)
    id_number_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="身份证号(哈希)")
    real_name_status: Mapped[int] = mapped_column(Integer, default=0, comment="实名状态(0=未实名 1=已实名)")
    company_name: Mapped[Optional[str]] = mapped_column(String(100), comment="企业名称(企业寄件)")
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, comment="账号年龄(天)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, comment="注册时间",
    )


# ============================================================
# 收件地址
# ============================================================

class Address(Base):
    """收件地址表: 一个用户可挂多个收件地址, 支持临时地址/常用地址"""
    __tablename__ = "address"

    address_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="地址ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="归属用户ID")
    receiver_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人姓名")
    receiver_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件人手机")
    province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="市")
    district: Mapped[str] = mapped_column(String(50), nullable=False, comment="区")
    street: Mapped[str] = mapped_column(String(200), nullable=False, comment="详细地址")
    is_temp: Mapped[int] = mapped_column(Integer, default=0, comment="是否临时地址(0/1)")
    use_count: Mapped[int] = mapped_column(Integer, default=0, comment="已使用次数")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, comment="创建时间",
    )


# ============================================================
# 运单主表
# ============================================================

class Shipment(Base):
    """运单主表: 1 条 = 1 次寄递. 覆盖普通/跨境/代收货款 3 种业务场景"""
    __tablename__ = "shipment"

    shipment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="运单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄件人用户ID")
    shipment_type: Mapped[str] = mapped_column(
        Enum("普通", "跨境", "代收货款", name="shipment_type_enum"),
        nullable=False, default="普通", comment="运单类型",
    )
    receiver_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人姓名")
    receiver_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件人手机")
    address_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件地址ID")
    origin_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄出省")
    dest_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的省")
    dest_city: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的市")
    dest_country: Mapped[Optional[str]] = mapped_column(String(50), comment="目的国家(跨境用)")
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="总重量(kg)")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="申报价值(元)")
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="代收货款金额(元)")
    is_dangerous_declared: Mapped[int] = mapped_column(Integer, default=0, comment="是否如实申报危险品(0/1)")
    is_delivered: Mapped[int] = mapped_column(Integer, default=0, comment="是否已送达(0/1)")
    is_rejected: Mapped[int] = mapped_column(Integer, default=0, comment="是否拒收(0/1, COD 用)")
    status: Mapped[str] = mapped_column(
        Enum("待揽收", "运输中", "已签收", "拒收", "已取消", name="shipment_status_enum"),
        default="待揽收", comment="运单状态",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, comment="下单/寄件时间",
    )


# ============================================================
# 运单物品明细
# ============================================================

class ShipmentItem(Base):
    """运单物品明细: 1 单 N 个物品, item_category 用于危险品识别"""
    __tablename__ = "shipment_item"

    item_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="明细ID")
    shipment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单ID")
    item_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="物品名称")
    item_category: Mapped[str] = mapped_column(
        Enum("普通", "电池", "液体", "化学品", name="item_category_enum"),
        nullable=False, default="普通", comment="物品类别",
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    unit_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="单件重量(kg)")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="单件价格(元)")


# ============================================================
# 物流行业扩展黑名单
# ============================================================

class BlacklistExtra(Base):
    """物流行业扩展黑名单: 身份证号 / 寄件网点 (RiskBlacklist 只覆盖 用户/地址/手机号)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    blacklist_type: Mapped[str] = mapped_column(
        Enum("身份证号", "寄件网点", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    blacklist_value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, comment="创建时间",
    )
