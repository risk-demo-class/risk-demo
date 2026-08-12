"""
旅游出行风控系统 - 旅游业务表 ORM 模型.

对应 db/init.sql 中 11 张业务表, 特征工程和规则引擎通过这些模型查询业务数据.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    """旅游用户信息表."""

    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[Optional[str]] = mapped_column(String(100), comment="用户姓名")
    real_name_status: Mapped[str] = mapped_column(
        Enum("未实名", "已实名", name="real_name_status_enum"),
        server_default="未实名",
        comment="实名状态",
    )
    vip_level: Mapped[str] = mapped_column(String(20), server_default="普通", comment="会员等级")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="注册时间")
    account_age_days: Mapped[int] = mapped_column(Integer, server_default="0", comment="账号年龄(天)")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="手机号")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_user_phone", "phone"),
        Index("idx_user_register_at", "register_at"),
    )


class DeviceFingerprint(Base):
    """设备指纹表."""

    __tablename__ = "device_fingerprint"

    fingerprint_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="设备指纹ID",
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(128), comment="设备指纹哈希")
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="首次出现时间")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近出现时间")
    os: Mapped[Optional[str]] = mapped_column(String(50), comment="操作系统")
    browser: Mapped[Optional[str]] = mapped_column(String(100), comment="浏览器")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="idx_device_user"),
        Index("idx_device_user_id", "user_id"),
        Index("idx_device_hash", "fingerprint_hash"),
    )


class OrderInfo(Base):
    """旅游订单主表."""

    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_type: Mapped[str] = mapped_column(
        Enum("机票", "酒店", "签证", "跟团游", "团票", name="order_type_enum"),
        nullable=False,
        comment="订单类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default="0",
        comment="订单总金额",
    )
    dest_country: Mapped[Optional[str]] = mapped_column(String(100), comment="目的地国家")
    depart_date: Mapped[Optional[date]] = mapped_column(Date, comment="出发日期")
    return_date: Mapped[Optional[date]] = mapped_column(Date, comment="返回日期")
    passenger_count: Mapped[int] = mapped_column(Integer, server_default="1", comment="乘客人数")
    pay_account: Mapped[Optional[str]] = mapped_column(String(100), comment="支付账号")
    device_id: Mapped[Optional[str]] = mapped_column(String(100), comment="下单设备ID")
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), comment="下单IP")
    order_remark: Mapped[Optional[str]] = mapped_column(String(1000), comment="订单备注")
    order_status: Mapped[str] = mapped_column(
        String(20),
        server_default="待支付",
        comment="订单状态",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="下单时间",
    )
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_order_user_id", "user_id"),
        Index("idx_order_create_time", "create_time"),
        Index("idx_order_pay_account", "pay_account"),
        Index("idx_order_device_id", "device_id"),
        Index("idx_order_dest_country", "dest_country"),
    )


class PassengerInfo(Base):
    """乘客信息表."""

    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="乘客ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="下单用户ID")
    name: Mapped[Optional[str]] = mapped_column(String(100), comment="乘客姓名")
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", "其他", name="passenger_id_type_enum"),
        server_default="身份证",
        comment="证件类型",
    )
    id_number: Mapped[Optional[str]] = mapped_column(String(64), comment="证件号码")
    passport_no: Mapped[Optional[str]] = mapped_column(String(64), comment="护照号码")
    nationality: Mapped[Optional[str]] = mapped_column(String(50), comment="国籍")
    age: Mapped[Optional[int]] = mapped_column(Integer, comment="年龄")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="联系电话")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_passenger_order_id", "order_id"),
        Index("idx_passenger_user_id", "user_id"),
        Index("idx_passenger_id_number", "id_number"),
        Index("idx_passenger_passport_no", "passport_no"),
    )


class BookingFlight(Base):
    """机票预订表."""

    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机票预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="航班号")
    depart_airport: Mapped[Optional[str]] = mapped_column(String(100), comment="出发机场")
    arrive_airport: Mapped[Optional[str]] = mapped_column(String(100), comment="到达机场")
    depart_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="起飞时间")
    cabin_class: Mapped[Optional[str]] = mapped_column(String(20), comment="舱位等级")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0", comment="票面金额")
    refundable: Mapped[int] = mapped_column(Integer, server_default="1", comment="是否可退")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_flight_order_id", "order_id"),
        Index("idx_flight_no_time", "flight_no", "depart_time"),
    )


class BookingHotel(Base):
    """酒店预订表."""

    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    hotel_name: Mapped[Optional[str]] = mapped_column(String(200), comment="酒店名称")
    check_in: Mapped[Optional[date]] = mapped_column(Date, comment="入住日期")
    check_out: Mapped[Optional[date]] = mapped_column(Date, comment="离店日期")
    room_count: Mapped[int] = mapped_column(Integer, server_default="1", comment="房间数")
    is_refundable: Mapped[int] = mapped_column(Integer, server_default="1", comment="是否可取消")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0", comment="预订金额")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_hotel_order_id", "order_id"),
        Index("idx_hotel_id", "hotel_id"),
    )


class VisaApplication(Base):
    """签证申请表."""

    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    dest_country: Mapped[str] = mapped_column(String(100), nullable=False, comment="目的地国家")
    visa_type: Mapped[Optional[str]] = mapped_column(String(50), comment="签证类型")
    passport_no: Mapped[Optional[str]] = mapped_column(String(64), comment="护照号")
    reject_history: Mapped[int] = mapped_column(Integer, server_default="0", comment="是否有拒签历史")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="提交时间")
    status: Mapped[str] = mapped_column(String(20), server_default="审核中", comment="签证状态")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_visa_user_id", "user_id"),
        Index("idx_visa_dest_country", "dest_country"),
        Index("idx_visa_submit_time", "submit_time"),
        Index("idx_visa_passport_no", "passport_no"),
    )


class TicketChangeApplication(Base):
    """机票退改申请表."""

    __tablename__ = "ticket_change_application"

    change_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退改申请ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    change_type: Mapped[str] = mapped_column(
        Enum("改签", "退票", "其他", name="change_type_enum"),
        nullable=False,
        comment="退改类型",
    )
    old_flight_no: Mapped[Optional[str]] = mapped_column(String(20), comment="原航班号")
    new_flight_no: Mapped[Optional[str]] = mapped_column(String(20), comment="新航班号")
    old_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0", comment="原票面金额")
    new_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0", comment="新票面金额")
    apply_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="申请时间")
    status: Mapped[str] = mapped_column(String(20), server_default="待审核", comment="处理状态")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_change_order_id", "order_id"),
        Index("idx_change_user_id", "user_id"),
        Index("idx_change_apply_time", "apply_time"),
    )


class HotelPreauthorization(Base):
    """酒店预授权表."""

    __tablename__ = "hotel_preauthorization"

    preauth_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="预授权ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    preauth_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default="0",
        comment="预授权金额",
    )
    actual_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default="0",
        comment="实际扣款金额",
    )
    status: Mapped[str] = mapped_column(
        Enum("待确认", "已确认", "已释放", "异常", name="preauth_status_enum"),
        server_default="待确认",
        comment="预授权状态",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_preauth_order_id", "order_id"),
        Index("idx_preauth_user_id", "user_id"),
        Index("idx_preauth_hotel_id", "hotel_id"),
    )


class GroupBooking(Base):
    """团票 / 拼团表."""

    __tablename__ = "group_booking"

    group_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="团票ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订单ID")
    leader_user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="团长用户ID")
    member_count: Mapped[int] = mapped_column(Integer, server_default="1", comment="参团人数")
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default="0",
        comment="团票总金额",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_group_order_id", "order_id"),
        Index("idx_group_leader_user_id", "leader_user_id"),
    )


class BlacklistExtra(Base):
    """旅游业务扩展黑名单表."""

    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="黑名单ID",
    )
    type: Mapped[str] = mapped_column(
        Enum("护照号", "签证号", "设备指纹", "支付账号", "IP", name="blacklist_extra_type_enum"),
        nullable=False,
        comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="软删除时间(NULL=未删)",
    )

    __table_args__ = (
        UniqueConstraint("type", "value", name="idx_blacklist_extra_type_value"),
        Index("idx_blacklist_extra_expire_at", "expire_at"),
    )
