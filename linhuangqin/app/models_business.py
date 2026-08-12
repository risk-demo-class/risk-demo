"""
二手交易平台物流侧风控系统 - 业务表 ORM (12 张)
注意：文件名虽为 models_business.py（历史遗留），内容已是物流业务表。
不改名是因为全项目 import 路径依赖，重命名需大改。

对标电商业务表 + 二手平台三段式物流模型 (A 卖家→验货中心, B 验货中心→买家, C 退货逆向),
字段设计兼顾后续风控特征计算 (卖家/买家画像 / 调包检测 / 验货质检 / 轨迹异常 / 退货逆向).
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
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 第一层: 基础维度表 (无外键依赖)
# ============================================================

class ShipperInfo(Base):
    """发件人(卖家)信息表 (对标电商 user_info, 卖家画像)"""
    __tablename__ = "shipper_info"

    shipper_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="卖家ID")
    shipper_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="卖家姓名")
    shipper_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="卖家手机号")
    shipper_id_card: Mapped[str] = mapped_column(String(50), comment="身份证号(加密存储,合规)")
    shipper_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="发件省")
    shipper_city: Mapped[str] = mapped_column(String(20), nullable=False, comment="发件市")
    shipper_district: Mapped[str] = mapped_column(String(20), nullable=False, comment="发件区")
    shipper_street: Mapped[str] = mapped_column(String(100), nullable=False, comment="发件详细地址")
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    # 卖家画像聚合字段 (特征计算时更新)
    trade_total: Mapped[int] = mapped_column(Integer, default=0, comment="历史交易量")
    dispute_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计纠纷数")
    cancel_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计取消单数")
    wb_total: Mapped[int] = mapped_column(Integer, default=0, comment="历史运单总数")
    complaint_total: Mapped[int] = mapped_column(Integer, default=0, comment="累计投诉次数")


class ConsigneeInfo(Base):
    """收件人(买家)信息表 (对标电商 receive_info, 买家画像)"""
    __tablename__ = "consignee_info"

    consignee_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="买家ID")
    consignee_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="买家姓名")
    consignee_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="买家手机号")
    consignee_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件省")
    consignee_city: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件市")
    consignee_district: Mapped[str] = mapped_column(String(20), nullable=False, comment="收件区")
    consignee_street: Mapped[str] = mapped_column(String(100), nullable=False, comment="收件详细地址")
    # 买家画像聚合字段 (特征计算时更新)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, comment="历史签收次数")
    return_count: Mapped[int] = mapped_column(Integer, default=0, comment="历史退货次数")
    return_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, comment="退货率")


class CarrierInfo(Base):
    """承运商/快递员信息表 (运力侧风险主体)"""
    __tablename__ = "carrier_info"

    carrier_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="快递员ID")
    carrier_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="快递员姓名")
    carrier_phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="联系电话")
    vehicle_plate: Mapped[Optional[str]] = mapped_column(String(20), comment="车牌号")
    vehicle_type: Mapped[Optional[str]] = mapped_column(
        Enum("厢式货车", "平板货车", "冷链车", "危化品车", "快递三轮车", name="vehicle_type_enum"),
        comment="车型",
    )
    vehicle_capacity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), comment="核定载重(kg)")
    qualification: Mapped[Optional[str]] = mapped_column(String(200), comment="资质证件(道路运输许可证等)")
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="保证金(元)")
    is_verified: Mapped[int] = mapped_column(Integer, default=0, comment="是否实名认证(0=未认证,1=已认证)")
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册/入驻时间")
    # 快递员画像聚合字段
    deliver_total: Mapped[int] = mapped_column(Integer, default=0, comment="历史配送量")
    photo_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, comment="签收拍照率")
    complaint_total: Mapped[int] = mapped_column(Integer, default=0, comment="累计投诉次数")


class DimensionCargoCategory(Base):
    """二手品类维度表 (手机/电脑/相机/奢侈品等, 高溢价标记)"""
    __tablename__ = "dimension_cargo_category"

    cargo_category: Mapped[str] = mapped_column(String(20), primary_key=True, comment="二手品类")
    is_high_value: Mapped[int] = mapped_column(Integer, default=0, comment="是否高溢价品类(手机/相机/奢侈品等, 调包高发)")


class DimensionWaybillStatus(Base):
    """运单状态维度表 (10 类物流事件状态码)"""
    __tablename__ = "dimension_waybill_status"

    waybill_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="运单状态")


class ComplaintReason(Base):
    """投诉原因表 (维度表)"""
    __tablename__ = "complaint_reason"

    complaint_reason: Mapped[str] = mapped_column(String(100), primary_key=True, comment="投诉原因")


# ============================================================
# 第二层: 核心业务表
# ============================================================

class WaybillInfo(Base):
    """运单主表 (三段式核心实体, 对标电商 order_info)"""
    __tablename__ = "waybill_info"

    waybill_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="运单号")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间(卖家下单寄件)")
    pickup_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="揽收入仓时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="买家签收时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")
    segment: Mapped[str] = mapped_column(
        Enum("A", "B", "C", name="waybill_segment_enum"),
        nullable=False, server_default="A", comment="当前所属链路(A=入仓/B=出仓/C=退货逆向)",
    )
    shipper_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="卖家ID")
    consignee_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="买家ID")
    carrier_id: Mapped[Optional[str]] = mapped_column(String(50), comment="快递员ID")
    waybill_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="运单状态")
    inspection_record_id: Mapped[Optional[str]] = mapped_column(String(50), comment="关联验货报告ID")
    seal_id: Mapped[Optional[str]] = mapped_column(String(50), comment="验货后封条/防拆贴ID")
    # 货物概要 (特征常用, 冗余在运单主表加速查询)
    cargo_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="二手品类")
    cargo_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="包裹重量(kg)")
    cargo_volume: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, comment="包裹体积(m³)")
    cargo_quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="货物件数")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="声明价值(元)")
    # 费用字段 (资金风险特征)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="运费(元)")
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="代收货款金额(COD,元)")
    insurance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="保价金额(元)")
    insurance_premium: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="保价费(元)")
    is_night_order: Mapped[int] = mapped_column(Integer, default=0, comment="是否夜间下单(0-6点)")
    is_urgent: Mapped[int] = mapped_column(Integer, default=0, comment="是否加急")
    cargo_type: Mapped[str] = mapped_column(
        Enum("普通", "电池", "化学品", "液体", "粉末", "刀具", "其他", name="cargo_type_enum"),
        nullable=False, server_default="普通", comment="货物类型(用于危险品检测)",
    )
    is_cross_border: Mapped[int] = mapped_column(Integer, default=0, comment="是否跨境(港澳台/国际)")

    __table_args__ = (
        Index("idx_wb_shipper", "shipper_id", "create_time"),
        Index("idx_wb_carrier", "carrier_id", "create_time"),
        Index("idx_wb_status", "waybill_status"),
        Index("idx_wb_category", "cargo_category"),
        Index("idx_wb_night", "is_night_order"),
        Index("idx_wb_cross", "is_cross_border"),
        Index("idx_wb_segment", "segment"),
    )


class WaybillDetail(Base):
    """运单明细表 (对标电商 order_detail, 物品明细含品牌/型号/成色)"""
    __tablename__ = "waybill_detail"

    detail_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="明细ID")
    waybill_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    item_imei: Mapped[Optional[str]] = mapped_column(String(50), comment="商品序列号/IMEI(关联 item_identity)")
    cargo_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="物品名称")
    item_brand: Mapped[str] = mapped_column(String(50), nullable=False, comment="品牌")
    item_model: Mapped[str] = mapped_column(String(50), nullable=False, comment="型号")
    item_grade: Mapped[str] = mapped_column(
        Enum("优", "良", "差", name="item_grade_enum"),
        nullable=False, server_default="良", comment="寄出时成色",
    )
    cargo_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="二手品类")
    cargo_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="重量(kg)")
    cargo_volume: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, comment="体积(m³)")
    cargo_quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="件数")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="声明价值(元)")

    __table_args__ = (
        Index("idx_wbd_waybill", "waybill_id"),
        Index("idx_wbd_imei", "item_imei"),
        Index("idx_wbd_category", "cargo_category"),
    )


class ItemIdentity(Base):
    """商品身份表 (调包检测核心, IMEI/序列号唯一绑定)"""
    __tablename__ = "item_identity"

    item_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="商品身份ID")
    item_imei: Mapped[str] = mapped_column(String(50), nullable=False, comment="IMEI/序列号")
    item_brand: Mapped[str] = mapped_column(String(50), nullable=False, comment="品牌")
    item_model: Mapped[str] = mapped_column(String(50), nullable=False, comment="型号")
    cargo_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="二手品类")
    declared_grade: Mapped[str] = mapped_column(
        Enum("优", "良", "差", name="item_grade_enum"),
        nullable=False, comment="寄出时卖家声明成色",
    )
    inspected_grade: Mapped[Optional[str]] = mapped_column(
        Enum("优", "良", "差", name="item_grade_enum"),
        comment="验货后成色(与声明对比)",
    )
    return_grade: Mapped[Optional[str]] = mapped_column(
        Enum("优", "良", "差", name="item_grade_enum"),
        comment="退货时成色(与出仓对比)",
    )
    waybill_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联运单号")
    status: Mapped[str] = mapped_column(
        Enum("在途", "已售", "退货中", "已退回", "已锁定", name="item_status_enum"),
        nullable=False, server_default="在途", comment="商品当前状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")

    __table_args__ = (
        Index("idx_ii_imei", "item_imei"),
        Index("idx_ii_waybill", "waybill_id"),
    )


class InspectionRecord(Base):
    """验货记录表 (验货环节特征核心)"""
    __tablename__ = "inspection_record"

    record_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="验货记录ID")
    waybill_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    item_imei: Mapped[str] = mapped_column(String(50), nullable=False, comment="商品序列号/IMEI")
    inspector_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="验货员ID")
    inspect_type: Mapped[str] = mapped_column(
        Enum("入仓验货", "出仓复验", "退货验货", name="inspect_type_enum"),
        nullable=False, comment="验货环节(入仓/出仓/退货)",
    )
    grade_result: Mapped[str] = mapped_column(
        Enum("优", "良", "差", name="item_grade_enum"),
        nullable=False, comment="验货成色结果",
    )
    functional_result: Mapped[str] = mapped_column(
        Enum("正常", "异常", name="functional_result_enum"),
        nullable=False, server_default="正常", comment="功能检测结果",
    )
    accessories_result: Mapped[str] = mapped_column(
        Enum("齐全", "缺失", name="accessories_result_enum"),
        nullable=False, server_default="齐全", comment="配件检测结果",
    )
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), comment="验货照片URL")
    video_url: Mapped[Optional[str]] = mapped_column(String(500), comment="验货视频URL")
    seal_id: Mapped[Optional[str]] = mapped_column(String(50), comment="封条ID")
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, comment="验货耗时(分钟)")
    inspect_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="验货时间")

    __table_args__ = (
        Index("idx_ir_waybill", "waybill_id"),
        Index("idx_ir_inspector", "inspector_id", "inspect_time"),
        Index("idx_ir_imei", "item_imei"),
    )


class TrackingEvent(Base):
    """轨迹事件表 (物流节点明细, 节点重量用于调包检测)"""
    __tablename__ = "tracking_event"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="事件ID")
    waybill_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    event_type: Mapped[str] = mapped_column(
        Enum("卖家下单寄件", "揽收入仓", "验货完成", "出仓发货",
             "运输中", "派送中", "买家签收", "买家拒收",
             "买家退回寄件", "退货入仓验货",
             name="tracking_event_type_enum"),
        nullable=False, comment="事件类型(三段式10类)",
    )
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="事件时间")
    location_province: Mapped[Optional[str]] = mapped_column(String(20), comment="所在省")
    location_city: Mapped[Optional[str]] = mapped_column(String(20), comment="所在市")
    location_district: Mapped[Optional[str]] = mapped_column(String(20), comment="所在区")
    location_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), comment="纬度")
    location_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), comment="经度")
    node_weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), comment="节点称重(kg, 调包检测)")
    operator_id: Mapped[Optional[str]] = mapped_column(String(50), comment="操作人ID(快递员/验货员)")
    remark: Mapped[Optional[str]] = mapped_column(String(200), comment="备注")

    __table_args__ = (
        Index("idx_te_waybill", "waybill_id", "event_type"),
        Index("idx_te_time", "waybill_id", "event_time"),
    )


class ComplaintClaim(Base):
    """投诉纠纷表 (对标电商 postsale+物流投诉, 含投诉方)"""
    __tablename__ = "complaint_claim"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="投诉/理赔ID")
    waybill_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    claimant: Mapped[str] = mapped_column(
        Enum("买家", "卖家", name="claimant_enum"),
        nullable=False, comment="投诉方",
    )
    claim_type: Mapped[str] = mapped_column(
        Enum("调包投诉", "成色不符", "退货争议", "未收到",
             "破损投诉", "遗失投诉", "费用争议", "其他",
             name="claim_type_enum"),
        nullable=False, comment="投诉/理赔类型",
    )
    claim_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="争议金额(元)")
    claim_reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="投诉/理赔原因")
    claim_status: Mapped[str] = mapped_column(
        Enum("待处理", "处理中", "已赔付", "已驳回", "已关闭",
             name="claim_status_enum"),
        nullable=False, comment="处理状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")

    __table_args__ = (
        Index("idx_cc_waybill", "waybill_id"),
        Index("idx_cc_type", "claim_type"),
        Index("idx_cc_status", "claim_status"),
        Index("idx_cc_claimant", "claimant"),
    )