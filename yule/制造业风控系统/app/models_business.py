"""
制造业风控系统 - 业务表 ORM (7 张)

场景 D「制造业风控」业务边界: 经销商订货 / 设备保修 / 采购订单 / 售后维修
核心欺诈风险: 跨区串货、保修期外套保、大额囤货、资质过期仍下单、维修费用虚高.

设计说明:
  - user_id 即经销商业务账号, 与 dealer_id 一一对应 (经销商角色), 风控系统以它为"用户"维度主体.
  - 每张表都冗余了风控特征计算最常用的字段 (金额/数量/区域/时间), 避免特征工程大量 JOIN.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户 / 产品基础
# ============================================================

class UserInfo(Base):
    """用户信息表 (经销商 / 终端用户 / 内部员工)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID(经销商账号)")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名/联系人")
    role: Mapped[str] = mapped_column(
        Enum("经销商", "终端用户", "内部员工", name="user_role_enum"),
        nullable=False, comment="角色",
    )
    dealer_level: Mapped[Optional[str]] = mapped_column(
        Enum("核心经销商", "授权经销商", "普通经销商", name="dealer_level_enum"),
        comment="经销商等级",
    )
    region: Mapped[str] = mapped_column(String(50), nullable=False, comment="所属区域(省)")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class Product(Base):
    """产品信息表 (制造业"商品" + 保修期)"""
    __tablename__ = "product"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="产品ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    model: Mapped[str] = mapped_column(String(50), nullable=False, comment="型号")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="品类(机床/注塑机/空压机等)")
    msrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="官方建议零售价 MSRP")
    warranty_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="保修期(月)")


class DealerInfo(Base):
    """经销商档案表 (全新表, 电商没有"经销商"概念)"""
    __tablename__ = "dealer_info"

    dealer_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="经销商ID")
    dealer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="经销商名称")
    region: Mapped[str] = mapped_column(String(50), nullable=False, comment="授权区域(省)")
    authorized_brands: Mapped[str] = mapped_column(String(200), nullable=False, comment="授权品牌(逗号分隔)")
    contract_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="合同开始时间")
    contract_end: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="合同到期时间")


# ============================================================
# 订货域
# ============================================================

class OrderInfo(Base):
    """经销商订货订单表 (电商 OrderInfo 是 C 端订单, 这里是 B 端经销订单)"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    dealer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="经销商ID")
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="产品ID")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="订货数量(台)")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="成交单价")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="订单总金额")
    ship_to_region: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货区域(省)")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")


# ============================================================
# 保修 / 维修域
# ============================================================

class WarrantyRecord(Base):
    """设备保修记录表 (全新表, 电商没有"保修")"""
    __tablename__ = "warranty_record"

    warranty_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="保修单ID")
    product_sn: Mapped[str] = mapped_column(String(50), nullable=False, comment="设备序列号 SN")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订货订单ID")
    issue_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="报修时间")
    issue_type: Mapped[str] = mapped_column(
        Enum("质量问题", "人为损坏", "正常保养", "以旧换新", name="issue_type_enum"),
        nullable=False, comment="报修类型",
    )
    repair_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="维修费用(元)")
    technician_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="维修工ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")


class CrossRegionReport(Base):
    """跨区串货举报记录表 (全新表: 串货举报)"""
    __tablename__ = "cross_region_report"

    report_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="举报ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="被举报订单ID")
    dealer_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="被举报经销商ID")
    ship_to_region: Mapped[str] = mapped_column(String(50), nullable=False, comment="实际发货区域")
    dealer_region: Mapped[str] = mapped_column(String(50), nullable=False, comment="经销商授权区域")
    reporter_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="举报人(内部员工ID)")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="举报时间")


# ============================================================
# 业务黑名单扩展表 (设备SN / 经销商ID / 维修工)
# ============================================================

class BlacklistExtra(Base):
    """业务黑名单扩展表 (与风控核心 risk_blacklist 互补, 偏业务侧台账)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    type: Mapped[str] = mapped_column(
        Enum("设备SN", "经销商ID", "维修工", name="blacklist_extra_type_enum"),
        nullable=False, comment="业务黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(100), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
