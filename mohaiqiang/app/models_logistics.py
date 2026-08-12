"""
物流行业风控 - 业务表 ORM (12 张)

设计目标:
  1. 以 logistics_waybill 运单表为核心, 关联寄件人/收件人/地址/网点/结算账户
  2. 字段与索引面向后续风控特征计算:
     - 高频寄件/凌晨寄件      -> waybill(sender_id, create_time) + event_record
     - 实名信息异常           -> sender/recipient 实名字段
     - 危险品瞒报             -> waybill 物品品类/价值/重量
     - 跨境重量/申报价值异常   -> customs_info + waybill
     - 代收货款拒收率         -> waybill.cod_amount + cod_settlement
     - 偏远/临时/共用地址      -> address.is_remote/is_temp/address_key
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 基础维度
# ============================================================

class LogisticsCustomerAccount(Base):
    """月结客户/结算账户"""
    __tablename__ = "logistics_customer_account"

    account_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="结算账户ID")
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="客户名称")
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), comment="联系电话")
    settlement_account: Mapped[Optional[str]] = mapped_column(String(100), comment="结算账户")
    credit_level: Mapped[str] = mapped_column(
        String(20), default="普通", comment="信用等级: 普通/良好/优秀/高风险",
    )
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="授信额度",
    )
    settlement_method: Mapped[str] = mapped_column(
        String(20), default="月结", comment="结算方式: 月结/预付/现结",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="正常", comment="状态: 正常/冻结/注销",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_customer_status", "status"),
    )


class LogisticsSender(Base):
    """寄件人 (含实名信息)"""
    __tablename__ = "logistics_sender"

    sender_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="寄件人ID")
    account_id: Mapped[Optional[str]] = mapped_column(
        String(50), comment="关联结算账户ID",
    )
    sender_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="寄件人姓名")
    sender_phone: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄件人手机号")
    id_card_no: Mapped[Optional[str]] = mapped_column(
        String(64), comment="身份证号(生产环境应加密/脱敏存储)",
    )
    company_name: Mapped[Optional[str]] = mapped_column(String(100), comment="企业名称")
    province: Mapped[Optional[str]] = mapped_column(String(50), comment="寄件省")
    city: Mapped[Optional[str]] = mapped_column(String(50), comment="寄件市")
    district: Mapped[Optional[str]] = mapped_column(String(50), comment="寄件区")
    street_address: Mapped[Optional[str]] = mapped_column(String(200), comment="寄件详细地址")
    is_real_name_verified: Mapped[int] = mapped_column(
        Integer, default=0, comment="是否实名认证: 0/1",
    )
    verify_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="实名认证时间")
    verify_fail_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="实名核验失败次数(实名异常特征)",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_sender_account_id", "account_id"),
        Index("idx_sender_phone", "sender_phone"),
        Index("idx_sender_realname", "is_real_name_verified"),
    )


class LogisticsRecipient(Base):
    """收件人 (含实名信息)"""
    __tablename__ = "logistics_recipient"

    recipient_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="收件人ID")
    recipient_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="收件人姓名")
    recipient_phone: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人手机号")
    is_real_name_verified: Mapped[int] = mapped_column(
        Integer, default=0, comment="是否实名认证: 0/1",
    )
    verify_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="实名认证时间")
    verify_fail_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="实名核验失败次数(实名异常特征)",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_recipient_phone", "recipient_phone"),
        Index("idx_recipient_realname", "is_real_name_verified"),
    )


class LogisticsAddress(Base):
    """收件地址 (偏远/临时/共用地址识别)"""
    __tablename__ = "logistics_address"

    address_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="地址ID")
    recipient_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人ID")
    province: Mapped[str] = mapped_column(String(50), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="市")
    district: Mapped[str] = mapped_column(String(50), nullable=False, comment="区")
    street_address: Mapped[str] = mapped_column(String(200), nullable=False, comment="详细地址")
    address_key: Mapped[str] = mapped_column(
        String(200), default="", comment="归一化地址键(省市区+详细地址), 识别多人共用地址",
    )
    is_remote: Mapped[int] = mapped_column(Integer, default=0, comment="是否偏远地区: 0/1")
    is_temp: Mapped[int] = mapped_column(Integer, default=0, comment="是否临时地址: 0/1")
    use_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计使用次数(可直接做地址活跃特征)",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_address_recipient", "recipient_id"),
        Index("idx_address_geo", "province", "city", "district"),
        Index("idx_address_key", "address_key"),
        Index("idx_address_remote", "is_remote", "is_temp"),
    )


class LogisticsOperator(Base):
    """网点/快递员"""
    __tablename__ = "logistics_operator"

    operator_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="操作员ID")
    operator_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名")
    phone: Mapped[Optional[str]] = mapped_column(String(50), comment="手机号")
    network_id: Mapped[Optional[str]] = mapped_column(String(50), comment="网点ID")
    network_name: Mapped[Optional[str]] = mapped_column(String(100), comment="网点名称")
    is_internal: Mapped[int] = mapped_column(Integer, default=1, comment="是否内部人员: 0/1")
    status: Mapped[str] = mapped_column(String(20), default="正常", comment="状态: 正常/停用/注销")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_operator_network", "network_id"),
        Index("idx_operator_status", "status"),
    )


# ============================================================
# 核心业务
# ============================================================

class LogisticsWaybill(Base):
    """运单主表 (风控特征计算核心)"""
    __tablename__ = "logistics_waybill"

    waybill_no: Mapped[str] = mapped_column(String(50), primary_key=True, comment="运单号")
    sender_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="寄件人ID")
    recipient_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件人ID")
    address_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收件地址ID")
    operator_id: Mapped[Optional[str]] = mapped_column(String(50), comment="揽收快递员ID")
    account_id: Mapped[Optional[str]] = mapped_column(String(50), comment="月结客户账户ID")
    item_name: Mapped[Optional[str]] = mapped_column(String(100), comment="物品名称")
    item_category: Mapped[str] = mapped_column(
        String(20), default="普通", comment="物品品类: 普通/电子产品/电池/化学品/液体/文件/其他",
    )
    declared_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="申报价值(元)",
    )
    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), default=0, comment="重量(kg)",
    )
    volume_cm3: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="体积(cm3)",
    )
    insured_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="保价金额",
    )
    freight_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="运费",
    )
    payment_method: Mapped[str] = mapped_column(
        String(20), default="寄付", comment="支付方式: 寄付/到付/月结",
    )
    cod_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="代收货款金额(COD)",
    )
    is_cross_border: Mapped[int] = mapped_column(Integer, default=0, comment="是否跨境: 0/1")
    status: Mapped[str] = mapped_column(
        String(20), default="已下单",
        comment="状态: 已下单/已揽收/运输中/清关中/派送中/已签收/拒收/退回/异常/已完结",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")
    pickup_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="揽收时间")
    sign_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_waybill_sender", "sender_id"),
        Index("idx_waybill_recipient", "recipient_id"),
        Index("idx_waybill_address", "address_id"),
        Index("idx_waybill_account", "account_id"),
        Index("idx_waybill_status", "status"),
        Index("idx_waybill_create_time", "create_time"),
        Index("idx_waybill_sender_create", "sender_id", "create_time"),       # 高频寄件
        Index("idx_waybill_recipient_create", "recipient_id", "create_time"),
        Index("idx_waybill_cross_status", "is_cross_border", "status"),      # 跨境+状态
        Index("idx_waybill_cod_amount", "cod_amount"),                        # COD 特征
    )


class LogisticsEventRecord(Base):
    """物流业务事件流水 (支撑事件型特征: 凌晨揽收/事件频次/轨迹)"""
    __tablename__ = "logistics_event_record"

    event_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="事件ID")
    waybill_no: Mapped[Optional[str]] = mapped_column(
        String(50), comment="关联运单号(部分事件无运单)",
    )
    sender_id: Mapped[Optional[str]] = mapped_column(String(50), comment="寄件人ID")
    recipient_id: Mapped[Optional[str]] = mapped_column(String(50), comment="收件人ID")
    operator_id: Mapped[Optional[str]] = mapped_column(String(50), comment="操作员ID")
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="事件类型: 寄件下单/揽收/中转/派送/签收/拒收/退回/投诉/理赔申请/异常上报/报关清关/海外仓/结汇退税/实名认证",
    )
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="事件时间")
    location: Mapped[Optional[str]] = mapped_column(String(100), comment="事件地点/网点")
    detail: Mapped[Optional[str]] = mapped_column(Text, comment="事件详情(JSON)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_event_waybill", "waybill_no"),
        Index("idx_event_type_time", "event_type", "event_time"),
        Index("idx_event_sender", "sender_id"),
        Index("idx_event_operator", "operator_id"),
        Index("idx_event_time", "event_time"),
    )


class LogisticsCustomsInfo(Base):
    """跨境报关信息"""
    __tablename__ = "logistics_customs_info"

    customs_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="报关ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    order_no: Mapped[Optional[str]] = mapped_column(String(50), comment="电商订单号")
    payment_no: Mapped[Optional[str]] = mapped_column(String(50), comment="支付单号")
    manifest_no: Mapped[Optional[str]] = mapped_column(String(50), comment="报关清单号")
    trade_mode: Mapped[str] = mapped_column(
        String(20), default="9610", comment="贸易方式: 9610/9710/9810/1210/一般贸易/其他",
    )
    hs_code: Mapped[Optional[str]] = mapped_column(String(20), comment="HS编码")
    declared_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, comment="申报价值",
    )
    currency: Mapped[str] = mapped_column(String(10), default="CNY", comment="币种")
    origin_country: Mapped[Optional[str]] = mapped_column(String(50), comment="原产国")
    destination_country: Mapped[Optional[str]] = mapped_column(String(50), comment="目的国")
    customs_status: Mapped[str] = mapped_column(
        String(20), default="待申报", comment="状态: 待申报/已申报/查验中/已放行/查验异常",
    )
    clear_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="放行时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_customs_waybill", "waybill_no", unique=True),
        Index("idx_customs_status", "customs_status"),
        Index("idx_customs_trade_mode", "trade_mode"),
        Index("idx_customs_hs_code", "hs_code"),
    )


class LogisticsCodSettlement(Base):
    """代收货款结算 (COD 拒收率特征)"""
    __tablename__ = "logistics_cod_settlement"

    cod_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="COD记录ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    account_id: Mapped[Optional[str]] = mapped_column(String(50), comment="结算账户ID")
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="代收金额")
    collect_status: Mapped[str] = mapped_column(
        String(20), default="待收款", comment="状态: 待收款/已收款/拒收/退款",
    )
    collect_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="收款时间")
    reject_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="拒收时间")
    settle_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="结算给寄件方时间")
    remark: Mapped[Optional[str]] = mapped_column(String(200), comment="备注")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_cod_waybill", "waybill_no"),
        Index("idx_cod_account", "account_id"),
        Index("idx_cod_status", "collect_status"),
        Index("idx_cod_collect_time", "collect_time"),
    )


class LogisticsClaim(Base):
    """理赔"""
    __tablename__ = "logistics_claim"

    claim_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="理赔ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    claim_type: Mapped[str] = mapped_column(
        String(20), default="其他", comment="类型: 丢件/破损/延误/其他",
    )
    claim_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="理赔金额")
    claim_reason: Mapped[Optional[str]] = mapped_column(Text, comment="理赔原因")
    claim_status: Mapped[str] = mapped_column(
        String(20), default="申请中", comment="状态: 申请中/定损中/已赔付/已驳回/已关闭",
    )
    apply_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="申请时间")
    settle_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="赔付时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_claim_waybill", "waybill_no"),
        Index("idx_claim_status", "claim_status"),
        Index("idx_claim_apply_time", "apply_time"),
    )


class LogisticsComplaint(Base):
    """投诉"""
    __tablename__ = "logistics_complaint_record"

    complaint_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="投诉ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    complaint_type: Mapped[str] = mapped_column(
        String(20), default="其他", comment="类型: 未收到/时效/服务/代收货款/其他",
    )
    complaint_content: Mapped[Optional[str]] = mapped_column(Text, comment="投诉内容")
    complaint_status: Mapped[str] = mapped_column(
        String(20), default="待处理", comment="状态: 待处理/处理中/已解决/已关闭",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    resolve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="解决时间")
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_complaint_waybill", "waybill_no"),
        Index("idx_complaint_status", "complaint_status"),
        Index("idx_complaint_create_time", "create_time"),
    )


class LogisticsAbnormalRecord(Base):
    """异常件记录"""
    __tablename__ = "logistics_abnormal_record"

    abnormal_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="异常记录ID")
    waybill_no: Mapped[str] = mapped_column(String(50), nullable=False, comment="运单号")
    abnormal_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="类型: 实名异常/危险品瞒报/重量价值异常/地址异常/COD拒收异常/清关异常/滞留异常/其他",
    )
    abnormal_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="异常时间")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="异常描述")
    handle_status: Mapped[str] = mapped_column(
        String(20), default="待处理", comment="状态: 待处理/已核实/已处置/已关闭",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_abnormal_waybill", "waybill_no"),
        Index("idx_abnormal_type", "abnormal_type"),
        Index("idx_abnormal_time", "abnormal_time"),
    )
