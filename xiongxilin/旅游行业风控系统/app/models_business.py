"""
旅游行业风控系统 - 业务表 ORM (10 张)

业务表只保存 OTA/旅行社交易链路中的原始业务数据。
风控事件、特征、评估、案件、黑名单和画像仍由 app.models_risk 负责。
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    """旅游平台用户基础信息"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户姓名")
    phone: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, comment="手机号")
    real_name_status: Mapped[str] = mapped_column(
        Enum("未实名", "已实名", "实名失败", name="travel_real_name_status_enum"),
        default="未实名", nullable=False, comment="实名状态",
    )
    vip_level: Mapped[str] = mapped_column(
        Enum("普通", "银卡", "金卡", "白金", name="travel_vip_level_enum"),
        default="普通", nullable=False, comment="会员等级",
    )
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="账号年龄(天)")
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    pay_account: Mapped[str] = mapped_column(String(80), nullable=False, comment="常用支付账号")
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, comment="常用设备指纹")
    login_ip: Mapped[Optional[str]] = mapped_column(String(45), comment="最近登录IP")
    source_channel: Mapped[str] = mapped_column(
        Enum("App", "小程序", "H5", "旅行社后台", name="travel_source_channel_enum"),
        default="App", nullable=False, comment="注册渠道",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class DestinationRisk(Base):
    """目的地风险字典"""
    __tablename__ = "destination_risk"

    destination_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="目的地ID")
    country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地城市")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", "极高", name="destination_risk_level_enum"),
        default="低", nullable=False, comment="目的地风险等级",
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="目的地风险分")
    risk_reason: Mapped[Optional[str]] = mapped_column(String(300), comment="风险原因")
    is_cross_border: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="是否跨境")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="更新时间")


class OrderInfo(Base):
    """旅游订单主表"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_type: Mapped[str] = mapped_column(
        Enum("跟团游", "自由行", "机票", "酒店", "签证", name="travel_order_type_enum"),
        nullable=False, comment="订单类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False, comment="订单总金额")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家")
    dest_city: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地城市")
    depart_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出发日期")
    return_date: Mapped[Optional[date]] = mapped_column(Date, comment="返回日期")
    passenger_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="旅客数")
    order_status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "已出票", "已确认", "已取消", "已完成", "退款中", "已退款",
             name="travel_order_status_enum"),
        default="待支付", nullable=False, comment="订单状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")
    pay_account: Mapped[str] = mapped_column(String(80), nullable=False, comment="支付账号")
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, comment="下单设备指纹")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), comment="下单IP")
    source_channel: Mapped[str] = mapped_column(
        Enum("App", "小程序", "H5", "旅行社后台", name="travel_order_source_channel_enum"),
        default="App", nullable=False, comment="订单来源",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class PassengerInfo(Base):
    """旅客与证件信息"""
    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="旅客ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="旅客姓名")
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", "港澳通行证", "台胞证", name="passenger_id_type_enum"),
        nullable=False, comment="证件类型",
    )
    id_number: Mapped[str] = mapped_column(String(80), nullable=False, comment="证件号")
    passport_no: Mapped[Optional[str]] = mapped_column(String(80), comment="护照号")
    nationality: Mapped[str] = mapped_column(String(50), default="中国", nullable=False, comment="国籍")
    age: Mapped[int] = mapped_column(Integer, default=18, nullable=False, comment="年龄")
    document_expire_date: Mapped[Optional[date]] = mapped_column(Date, comment="证件有效期")
    document_status: Mapped[str] = mapped_column(
        Enum("有效", "即将过期", "已过期", "疑似冒用", name="document_status_enum"),
        default="有效", nullable=False, comment="证件状态",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class VisaApplication(Base):
    """签证申请表"""
    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="签证国家")
    visa_type: Mapped[str] = mapped_column(
        Enum("旅游签", "商务签", "探亲签", "过境签", name="visa_type_enum"),
        default="旅游签", nullable=False, comment="签证类型",
    )
    reject_history: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="历史拒签次数")
    submit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="提交时间")
    visa_status: Mapped[str] = mapped_column(
        Enum("申请中", "通过", "拒签", "补材料", "撤销", name="visa_status_enum"),
        default="申请中", nullable=False, comment="签证状态",
    )
    material_change_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="材料变更次数")
    reject_reason: Mapped[Optional[str]] = mapped_column(String(300), comment="拒签原因")
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class BookingHotel(Base):
    """酒店预订表"""
    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    hotel_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="酒店名称")
    city: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店城市")
    check_in: Mapped[date] = mapped_column(Date, nullable=False, comment="入住日期")
    check_out: Mapped[date] = mapped_column(Date, nullable=False, comment="离店日期")
    room_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="房间数")
    night_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="入住晚数")
    is_refundable: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="是否可退款")
    guest_document_status: Mapped[str] = mapped_column(
        Enum("有效", "缺失", "不一致", "疑似冒用", name="guest_document_status_enum"),
        default="有效", nullable=False, comment="入住人证件状态",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class BookingFlight(Base):
    """机票预订表"""
    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机票预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    flight_no: Mapped[str] = mapped_column(String(30), nullable=False, comment="航班号")
    airline: Mapped[str] = mapped_column(String(50), nullable=False, comment="航司")
    depart_airport: Mapped[str] = mapped_column(String(20), nullable=False, comment="出发机场")
    arrive_airport: Mapped[str] = mapped_column(String(20), nullable=False, comment="到达机场")
    depart_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="起飞时间")
    cabin_class: Mapped[str] = mapped_column(
        Enum("经济舱", "超级经济舱", "商务舱", "头等舱", name="cabin_class_enum"),
        default="经济舱", nullable=False, comment="舱位",
    )
    ticket_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="票数")
    refund_rule: Mapped[str] = mapped_column(
        Enum("不可退", "有条件退", "免费退", name="flight_refund_rule_enum"),
        default="有条件退", nullable=False, comment="退改规则",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class TravelRefund(Base):
    """旅游售后/退款/退改签申请"""
    __tablename__ = "travel_refund"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="售后退款ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    refund_type: Mapped[str] = mapped_column(
        Enum("退款", "改签", "取消", "补偿", name="travel_refund_type_enum"),
        default="退款", nullable=False, comment="售后类型",
    )
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False, comment="退款金额")
    refund_reason: Mapped[str] = mapped_column(String(300), nullable=False, comment="售后原因")
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    refund_status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过", "已拒绝", "已完成", name="travel_refund_status_enum"),
        default="待审核", nullable=False, comment="售后状态",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class TravelComplaint(Base):
    """投诉与赔付记录"""
    __tablename__ = "travel_complaint"

    complaint_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="投诉ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    complaint_type: Mapped[str] = mapped_column(
        Enum("行程变更", "酒店问题", "航班延误", "签证问题", "服务态度", "重复索赔",
             name="travel_complaint_type_enum"),
        nullable=False, comment="投诉类型",
    )
    complaint_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投诉时间")
    compensation_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False, comment="赔付金额")
    complaint_status: Mapped[str] = mapped_column(
        Enum("待处理", "处理中", "已赔付", "已驳回", "已关闭", name="travel_complaint_status_enum"),
        default="待处理", nullable=False, comment="投诉状态",
    )
    risk_label: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="训练标签")


class BlacklistExtra(Base):
    """旅游业务黑名单扩展表"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="扩展黑名单ID")
    type: Mapped[str] = mapped_column(
        Enum("用户", "手机号", "护照号", "身份证号", "支付账号", "设备指纹", "IP", "订单",
             name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(120), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(300), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    risk_label: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="训练标签")
