"""制造业设备经销商风控系统 - 业务表 ORM（第一版 6 张）。

业务模型只提供风控所需的经销商、设备、采购、保修、串货和扩展黑名单数据。
九张核心风控表仍由 ``app.models_risk`` 独立管理。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Dealer(Base):
    """设备制造商签约经销商。"""

    __tablename__ = "dealer"

    dealer_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="经销商ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="经销商名称")
    level: Mapped[str] = mapped_column(
        Enum("普通", "核心", "战略", name="dealer_level_enum"),
        nullable=False,
        server_default="普通",
        comment="经销商等级",
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False, comment="授权经营区域")
    authorized_at: Mapped[date] = mapped_column(Date, nullable=False, comment="授权日期")
    contract_end: Mapped[date] = mapped_column(Date, nullable=False, comment="合同到期日")

    __table_args__ = (
        Index("uq_dealer_name", "name", unique=True),
        Index("idx_dealer_region", "region"),
        Index("idx_dealer_contract_end", "contract_end"),
    )


class Device(Base):
    """已生产并可追踪流向的设备。"""

    __tablename__ = "device"

    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备ID")
    sn: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备序列号")
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备型号")
    batch_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="生产批次")
    factory_at: Mapped[date] = mapped_column(Date, nullable=False, comment="出厂日期")
    warranty_end: Mapped[date] = mapped_column(Date, nullable=False, comment="保修到期日")
    # 可空：设备尚未出库时没有归属经销商；出库后用于串货报告反查责任经销商。
    dealer_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("dealer.dealer_id", name="fk_device_dealer"),
        nullable=True, comment="当前归属经销商ID",
    )

    __table_args__ = (
        Index("uq_device_sn", "sn", unique=True),
        Index("idx_device_model", "model"),
        Index("idx_device_batch_no", "batch_no"),
        Index("idx_device_dealer_id", "dealer_id"),
    )


class PurchaseOrder(Base):
    """经销商采购订单；第一版以 JSON 保存采购设备汇总。"""

    __tablename__ = "purchase_order"

    po_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="采购订单ID")
    dealer_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("dealer.dealer_id", name="fk_purchase_order_dealer"),
        nullable=False, comment="经销商ID",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, comment="采购总金额",
    )
    items: Mapped[dict | list] = mapped_column(JSON, nullable=False, comment="采购设备明细(JSON)")
    ship_to: Mapped[str] = mapped_column(String(200), nullable=False, comment="交付区域或地址")
    payment_term: Mapped[str] = mapped_column(
        Enum("预付", "账期30天", "账期60天", name="purchase_payment_term_enum"),
        nullable=False,
        comment="付款条件",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="采购单创建时间",
    )

    __table_args__ = (
        Index("idx_purchase_order_dealer_id", "dealer_id"),
        Index("idx_purchase_order_create_time", "create_time"),
        Index("idx_purchase_order_total_amount", "total_amount"),
    )


class WarrantyClaim(Base):
    """设备保修申请。"""

    __tablename__ = "warranty_claim"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="保修申请ID")
    device_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("device.device_id", name="fk_warranty_claim_device"),
        nullable=False, comment="设备ID",
    )
    dealer_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("dealer.dealer_id", name="fk_warranty_claim_dealer"),
        nullable=False, comment="申请经销商ID",
    )
    fault_desc: Mapped[str] = mapped_column(Text, nullable=False, comment="故障描述")
    claim_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, comment="索赔金额",
    )
    photos: Mapped[Optional[list | dict]] = mapped_column(JSON, nullable=True, comment="凭证照片(JSON)")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="申请时间",
    )

    __table_args__ = (
        Index("idx_warranty_claim_device_id", "device_id"),
        Index("idx_warranty_claim_dealer_id", "dealer_id"),
        Index("idx_warranty_claim_create_time", "create_time"),
    )


class CrossRegionReport(Base):
    """设备跨授权区域销售或流通举报。"""

    __tablename__ = "cross_region_report"

    report_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="串货举报ID")
    device_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("device.device_id", name="fk_cross_region_report_device"),
        nullable=False, comment="设备ID",
    )
    expected_region: Mapped[str] = mapped_column(String(100), nullable=False, comment="授权区域")
    actual_region: Mapped[str] = mapped_column(String(100), nullable=False, comment="实际发现区域")
    reporter_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="举报人或来源ID")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="举报时间",
    )

    __table_args__ = (
        Index("idx_cross_region_report_device_id", "device_id"),
        Index("idx_cross_region_report_regions", "expected_region", "actual_region"),
        Index("idx_cross_region_report_create_time", "create_time"),
    )


class BlacklistExtra(Base):
    """核心黑名单以外的企业证照、银行账户等补充标识。"""

    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="扩展黑名单ID")
    type: Mapped[str] = mapped_column(
        Enum("统一社会信用代码", "营业执照", "银行账户", "联系人手机号", name="blacklist_extra_type_enum"),
        nullable=False,
        comment="扩展标识类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="扩展标识值")
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="到期时间(NULL=永久)")

    __table_args__ = (
        Index("uq_blacklist_extra_type_value", "type", "value", unique=True),
        Index("idx_blacklist_extra_expire_at", "expire_at"),
    )
