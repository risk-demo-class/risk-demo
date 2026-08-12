"""
制造业风控系统 - 业务表 ORM (7 张)
只读映射业务系统的核心实体 (用户/产品/经销商/订货/保修/串货举报/业务黑名单)
不参与风控决策本身, 但被特征工程和规则引擎查询
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与产品基础
# ============================================================

class UserInfo(Base):
    """用户信息表: 经销商 / 终端用户 / 内部员工"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名/企业名")
    role: Mapped[str] = mapped_column(
        Enum("经销商", "终端用户", "内部员工", name="user_role_enum"),
        nullable=False, comment="用户角色",
    )
    dealer_level: Mapped[Optional[str]] = mapped_column(
        Enum("一级", "二级", "三级", name="dealer_level_enum"), comment="经销商等级",
    )
    region: Mapped[Optional[str]] = mapped_column(String(50), comment="所属区域")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="注册时间")


class Product(Base):
    """产品表: 制造业"商品" + 官方价 MSRP + 保修期"""
    __tablename__ = "product"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="产品ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    model: Mapped[Optional[str]] = mapped_column(String(100), comment="型号")
    category: Mapped[Optional[str]] = mapped_column(String(50), comment="产品类别")
    msrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="官方建议零售价")
    warranty_months: Mapped[int] = mapped_column(Integer, default=12, comment="保修期(月)")


class DealerInfo(Base):
    """经销商档案表 (全新表)"""
    __tablename__ = "dealer_info"

    dealer_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="经销商ID")
    dealer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="经销商名称")
    region: Mapped[str] = mapped_column(String(50), nullable=False, comment="授权区域")
    authorized_brands: Mapped[Optional[str]] = mapped_column(String(200), comment="授权品牌")
    contract_start: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="合同开始时间")
    contract_end: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="合同结束时间")


# ============================================================
# 订货域
# ============================================================

class OrderInfo(Base):
    """订货单表: 单产品订单 (直接挂 product_id, 无明细表)"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    dealer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="经销商ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="成交单价")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="订单总金额")
    ship_to_region: Mapped[Optional[str]] = mapped_column(String(50), comment="收货区域")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")

    __table_args__ = (
        Index("idx_order_dealer_id", "dealer_id"),
        Index("idx_order_create_time", "create_time"),
    )


class WarrantyRecord(Base):
    """保修记录表 (全新表: 电商版没有保修)"""
    __tablename__ = "warranty_record"

    warranty_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="保修单ID")
    product_sn: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备序列号(SN)")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订单ID")
    issue_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请/维修时间")
    issue_type: Mapped[str] = mapped_column(
        Enum("保修申请", "维修", name="warranty_issue_type_enum"),
        nullable=False, comment="单据类型",
    )
    repair_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="维修费用(申请时为0)",
    )
    technician_id: Mapped[Optional[str]] = mapped_column(String(50), comment="维修工ID")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="创建时间")

    __table_args__ = (
        Index("idx_warranty_sn", "product_sn"),
        Index("idx_warranty_order_id", "order_id"),
    )


class CrossRegionReport(Base):
    """跨区串货举报表 (全新表)"""
    __tablename__ = "cross_region_report"

    report_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="举报ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="被举报订单ID")
    dealer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="被举报经销商ID")
    ship_to_region: Mapped[Optional[str]] = mapped_column(String(50), comment="实际收货区域")
    dealer_region: Mapped[Optional[str]] = mapped_column(String(50), comment="经销商授权区域")
    reporter_id: Mapped[Optional[str]] = mapped_column(String(50), comment="举报人ID")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="举报时间")

    __table_args__ = (
        Index("idx_report_order_id", "order_id"),
    )


class BlacklistExtra(Base):
    """业务黑名单扩展表: 设备SN / 经销商ID / 维修工"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="黑名单条目ID")
    type: Mapped[str] = mapped_column(
        Enum("设备SN", "经销商ID", "维修工", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(100), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="创建时间")
