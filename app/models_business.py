"""
制造业风控系统 - 行业业务表 ORM (7 张)
业务边界: 经销商订货 / 采购订单 / 设备保修 / 售后维修 (任务书场景 D)

跟电商版的差异:
  - 订单主体从 C 端用户换成 B 端经销商 (dealer_id)
  - 商品换成设备 (Product, 带 MSRP + 保修月数)
  - 售后换成保修/维修工单 (WarrantyRecord, 按设备 SN 管理)
  - 新增跨区串货举报 (CrossRegionReport) 与行业黑名单扩展 (BlacklistExtra)

风控核心 9 张表完全复用, 业务层只读本文件, 被特征工程和规则引擎查询.
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
# 用户 / 经销商 / 产品基础
# ============================================================

class UserInfo(Base):
    """用户信息表: 经销商 / 终端用户 / 内部员工 (user_id 与 dealer_id 共用)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID(经销商时=dealer_id)")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名/企业联系人")
    role: Mapped[str] = mapped_column(
        Enum("经销商", "终端用户", "内部员工", name="mf_role_enum"),
        nullable=False, comment="角色",
    )
    dealer_level: Mapped[Optional[str]] = mapped_column(
        Enum("一级", "二级", "三级", name="mf_dealer_level_enum"),
        comment="经销商等级",
    )
    region: Mapped[Optional[str]] = mapped_column(String(50), comment="授权区域")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="联系电话")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class Product(Base):
    """产品表: 制造业"商品", 带官方建议零售价 MSRP 与保修月数"""
    __tablename__ = "product"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="产品ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    model: Mapped[str] = mapped_column(String(50), nullable=False, comment="型号")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="品类")
    msrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="官方建议零售价")
    warranty_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="保修月数")


class DealerInfo(Base):
    """经销商档案表: 全新表, 电商没有 '经销商' 概念"""
    __tablename__ = "dealer_info"

    dealer_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="经销商ID")
    dealer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="经销商名称")
    region: Mapped[str] = mapped_column(String(50), nullable=False, comment="授权区域")
    authorized_brands: Mapped[str] = mapped_column(String(200), nullable=False, comment="授权品牌")
    contract_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="合同开始")
    contract_end: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="合同到期")
    status: Mapped[str] = mapped_column(
        Enum("合作中", "已终止", name="mf_dealer_status_enum"),
        nullable=False, default="合作中", comment="合作状态",
    )


# ============================================================
# 订货域
# ============================================================

class OrderInfo(Base):
    """订货/采购订单表: 经销商向制造企业下单"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    order_type: Mapped[str] = mapped_column(
        Enum("经销商订货", "采购订单", name="mf_order_type_enum"),
        nullable=False, comment="订单类型",
    )
    dealer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="经销商ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品ID")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="订购数量")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="成交单价")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="订单总额")
    ship_to_region: Mapped[str] = mapped_column(String(50), nullable=False, comment="发货区域")
    order_status: Mapped[str] = mapped_column(
        Enum("待发货", "已发货", "已完成", "已取消", name="mf_order_status_enum"),
        nullable=False, comment="订单状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")


# ============================================================
# 保修 / 售后域
# ============================================================

class WarrantyRecord(Base):
    """保修/维修工单表: 全新表, 电商没有 '保修' 概念, 按设备 SN 管理"""
    __tablename__ = "warranty_record"

    warranty_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="工单ID")
    product_sn: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备序列号")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订货单ID")
    issue_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="报修时间")
    issue_type: Mapped[str] = mapped_column(
        Enum("保修", "维修", name="mf_issue_type_enum"),
        nullable=False, comment="工单类型",
    )
    repair_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="维修费用")
    technician_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="维修工ID")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="故障描述")


class CrossRegionReport(Base):
    """跨区串货举报表: 全新表, 电商没有 '串货' 概念"""
    __tablename__ = "cross_region_report"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="举报ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="被举报订单ID")
    dealer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="被举报经销商ID")
    ship_to_region: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单发货区域")
    dealer_region: Mapped[str] = mapped_column(String(50), nullable=False, comment="经销商授权区域")
    reporter_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="举报人ID")
    report_status: Mapped[str] = mapped_column(
        Enum("待核实", "已核实", "无效", name="mf_report_status_enum"),
        nullable=False, default="待核实", comment="核实状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="举报时间")


# ============================================================
# 行业黑名单扩展
# ============================================================

class BlacklistExtra(Base):
    """行业黑名单扩展表: type 加 经销商ID / 设备SN / 维修工 (任务书 D.1)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    type: Mapped[str] = mapped_column(
        Enum("经销商", "设备SN", "维修工", name="mf_blacklist_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
