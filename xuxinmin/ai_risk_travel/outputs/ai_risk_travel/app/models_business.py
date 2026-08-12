"""
旅游风控系统 - 业务表 ORM (7 张)

跟电商版完全不同的行业业务层:
  user_info        用户 (实名状态 / VIP 等级 / 账号年龄)
  order_info       订单 (目的地国家 / 出行日期 / 乘客数 / 订单类型)
  passenger_info   乘客 (1 订单 N 乘客, 身份证/护照号)
  visa_application 签证申请 (拒签历史 / 申请国家)
  booking_flight   机票预订 (航班 / 起降机场 / 舱位)
  booking_hotel    酒店预订 (入住 / 离店 / 可退)
  blacklist_extra  行业黑名单扩展 (护照号 / 签证号 / 设备指纹等)

风控特征 / 规则 / 校验都只读这套业务表, 不碰 9 张风控核心表.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    """用户信息表 (OTA 平台用户, 含实名状态)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户姓名")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="身份证号哈希(脱敏)")
    real_name_status: Mapped[int] = mapped_column(Integer, default=0, comment="实名状态(0=未实名,1=已实名)")
    vip_level: Mapped[int] = mapped_column(Integer, default=0, comment="VIP等级(0-5)")
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, comment="账号注册天数")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class OrderInfo(Base):
    """订单表 (机票/酒店/签证/跟团游)"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_type: Mapped[str] = mapped_column(
        Enum("机票", "酒店", "签证", "跟团游", name="travel_order_type_enum"),
        nullable=False, comment="订单类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单总金额")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家")
    depart_date: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="出发日期")
    return_date: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="返程日期")
    passenger_count: Mapped[int] = mapped_column(Integer, default=1, comment="乘客数")
    order_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="订单状态(待支付/已支付/已出票/已退订/已取消)")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")

    __table_args__ = (
        Index("idx_order_user_create", "user_id", "create_time"),
        Index("idx_order_dest_country", "dest_country"),
    )


class PassengerInfo(Base):
    """乘客信息表 (1 订单 N 乘客, 等价电商 ReceiveInfo 的位置)"""
    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="乘客ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="乘客姓名")
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", name="passenger_id_type_enum"),
        nullable=False, comment="证件类型",
    )
    id_number: Mapped[str] = mapped_column(String(64), nullable=False, comment="证件号")
    nationality: Mapped[str] = mapped_column(String(50), default="中国", comment="国籍")
    age: Mapped[int] = mapped_column(Integer, default=30, comment="年龄")

    __table_args__ = (
        Index("idx_passenger_order", "order_id"),
        Index("idx_passenger_id_number", "id_number"),
    )


class VisaApplication(Base):
    """签证申请表 (电商没有"签证"概念, 全新表)"""
    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="申请国家")
    visa_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="签证类型(旅游/商务/探亲)")
    reject_history: Mapped[int] = mapped_column(Integer, default=0, comment="该用户历史拒签次数")
    visa_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="状态(审核中/通过/被拒)")
    submit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="提交时间")

    __table_args__ = (
        Index("idx_visa_user_submit", "user_id", "submit_time"),
        Index("idx_visa_dest_country", "dest_country"),
    )


class BookingFlight(Base):
    """机票预订表"""
    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机票预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="航班号")
    depart_airport: Mapped[str] = mapped_column(String(50), nullable=False, comment="出发机场")
    arrive_airport: Mapped[str] = mapped_column(String(50), nullable=False, comment="到达机场")
    depart_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="起飞时间")
    cabin_class: Mapped[str] = mapped_column(
        Enum("经济舱", "公务舱", "头等舱", name="cabin_class_enum"),
        default="经济舱", comment="舱位等级",
    )

    __table_args__ = (
        Index("idx_flight_order", "order_id"),
        Index("idx_flight_no_time", "flight_no", "depart_time"),
    )


class BookingHotel(Base):
    """酒店预订表"""
    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    check_in: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="入住时间")
    check_out: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="离店时间")
    room_count: Mapped[int] = mapped_column(Integer, default=1, comment="房间数")
    is_refundable: Mapped[int] = mapped_column(Integer, default=1, comment="是否可退(0/1)")

    __table_args__ = (
        Index("idx_hotel_order", "order_id"),
    )


class BlacklistExtra(Base):
    """行业黑名单扩展表 (跟 risk_blacklist 并存, 供业务侧查询/演示)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="类型(护照号/签证号/设备指纹/身份证号/IP)")
    entry_value: Mapped[str] = mapped_column(String(200), nullable=False, comment="值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")

    __table_args__ = (
        Index("idx_blacklist_extra_type_value", "entry_type", "entry_value"),
    )
