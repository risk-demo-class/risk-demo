"""
旅游风控系统 - 业务表 ORM（7 张）
映射 OTA 平台的用户、订单、乘客、签证、酒店、航班与业务黑名单扩展数据。
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与订单
# ============================================================

class UserInfo(Base):
    """OTA 用户信息表。"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户名称")
    real_name_status: Mapped[str] = mapped_column(
        Enum("未实名", "已实名", "已认证", name="real_name_status_enum"),
        nullable=False,
        comment="实名状态",
    )
    vip_level: Mapped[int] = mapped_column(Integer, nullable=False, comment="会员等级")
    account_age_days: Mapped[int] = mapped_column(Integer, nullable=False, comment="账户注册天数")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class OrderInfo(Base):
    """旅游订单表。"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_type: Mapped[str] = mapped_column(
        Enum("机票", "酒店", "签证", "跟团游", name="order_type_enum"),
        nullable=False,
        comment="订单类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="订单总金额")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家或地区")
    depart_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出发或入住日期")
    return_date: Mapped[date] = mapped_column(Date, nullable=False, comment="返回或离店日期")
    passenger_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="乘客或入住人数")
    book_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")


# ============================================================
# 出行人与签证
# ============================================================

class PassengerInfo(Base):
    """订单乘客信息表（一单可对应多名乘客）。"""
    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="乘客ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="乘客姓名")
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", "港澳通行证", name="passenger_id_type_enum"),
        nullable=False,
        comment="证件类型",
    )
    id_number: Mapped[str] = mapped_column(String(100), nullable=False, comment="脱敏证件号")
    nationality: Mapped[str] = mapped_column(String(50), nullable=False, comment="国籍")
    age: Mapped[int] = mapped_column(Integer, nullable=False, comment="年龄")


class VisaApplication(Base):
    """签证申请表。"""
    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="签证目的国")
    visa_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="签证类型")
    reject_history: Mapped[int] = mapped_column(Integer, nullable=False, comment="历史拒签次数")
    submit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="提交时间")


# ============================================================
# 酒店与航班预订
# ============================================================

class BookingHotel(Base):
    """酒店预订明细表。"""
    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    check_in: Mapped[date] = mapped_column(Date, nullable=False, comment="入住日期")
    check_out: Mapped[date] = mapped_column(Date, nullable=False, comment="离店日期")
    room_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="房间数")
    is_refundable: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否可退")


class BookingFlight(Base):
    """航班预订明细表。"""
    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="航班预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="航班号")
    depart_airport: Mapped[str] = mapped_column(String(50), nullable=False, comment="出发机场")
    arrive_airport: Mapped[str] = mapped_column(String(50), nullable=False, comment="到达机场")
    cabin_class: Mapped[str] = mapped_column(String(20), nullable=False, comment="舱位等级")


# ============================================================
# 业务黑名单补充信息
# ============================================================

class BlacklistExtra(Base):
    """旅游行业证件、设备等业务黑名单扩展表。"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="扩展黑名单条目ID")
    type: Mapped[str] = mapped_column(
        Enum("护照号", "签证号", "设备指纹", "手机号", name="blacklist_extra_type_enum"),
        nullable=False,
        comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(128), nullable=False, comment="黑名单值")
    reason: Mapped[str] = mapped_column(String(255), nullable=False, comment="列入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间")
