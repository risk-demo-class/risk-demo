"""
旅游风控系统 - 业务表 ORM (7 张)
OTA 行业业务实体: 用户/订单/乘客/签证/航班/酒店/扩展黑名单
只被特征工程和规则引擎查询, 不参与风控决策本身
"""
from datetime import datetime
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与基础
# ============================================================

class UserInfo(Base):
    """用户表 (游客账号)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[Optional[str]] = mapped_column(String(50), comment="姓名/昵称")
    real_name_status: Mapped[str] = mapped_column(
        Enum("未实名", "已实名", name="real_name_status_enum"),
        default="未实名", comment="实名状态 (旅游必须)",
    )
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="身份证号哈希(脱敏)")
    vip_level: Mapped[int] = mapped_column(Integer, default=0, comment="会员等级 0-5")
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, comment="注册天数")
    register_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="注册时间")

    __table_args__ = (Index("idx_user_idcard_hash", "id_card_hash"),)


# ============================================================
# 订单域
# ============================================================

class OrderInfo(Base):
    """旅游订单主表 (机票/酒店/跟团游)"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_type: Mapped[str] = mapped_column(
        Enum("机票", "酒店", "跟团游", name="order_type_enum"),
        nullable=False, comment="订单类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单总金额")
    dest_country: Mapped[Optional[str]] = mapped_column(String(50), comment="目的地国家")
    depart_date: Mapped[Optional[datetime]] = mapped_column(Date, comment="出发日期")
    return_date: Mapped[Optional[datetime]] = mapped_column(Date, comment="返程日期")
    passenger_count: Mapped[int] = mapped_column(Integer, default=1, comment="乘客数")
    pay_status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "已取消", name="order_pay_status_enum"),
        default="待支付", comment="支付状态",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="下单时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")

    __table_args__ = (
        Index("idx_order_user_id", "user_id"),
        Index("idx_order_create_time", "create_time"),
    )


class PassengerInfo(Base):
    """乘客表 (1 个订单 N 个乘客)"""
    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="乘客ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="乘客姓名")
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", "其他", name="passenger_id_type_enum"),
        default="身份证", comment="证件类型",
    )
    id_number: Mapped[str] = mapped_column(String(50), nullable=False, comment="证件号")
    nationality: Mapped[Optional[str]] = mapped_column(String(50), comment="国籍")
    age: Mapped[Optional[int]] = mapped_column(Integer, comment="年龄")

    __table_args__ = (
        Index("idx_passenger_order_id", "order_id"),
        Index("idx_passenger_id_number", "id_number"),
    )


# ============================================================
# 签证域
# ============================================================

class VisaApplication(Base):
    """签证申请表"""
    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家")
    visa_type: Mapped[str] = mapped_column(String(30), default="旅游签证", comment="签证类型")
    reject_history: Mapped[int] = mapped_column(Integer, default=0, comment="历史拒签次数")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="提交时间")

    __table_args__ = (Index("idx_visa_user_id", "user_id"),)


# ============================================================
# 预订明细域
# ============================================================

class BookingFlight(Base):
    """机票预订明细表"""
    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机票预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="航班号")
    depart_airport: Mapped[Optional[str]] = mapped_column(String(20), comment="出发机场")
    arrive_airport: Mapped[Optional[str]] = mapped_column(String(20), comment="到达机场")
    cabin_class: Mapped[str] = mapped_column(
        Enum("经济舱", "公务舱", "头等舱", name="cabin_class_enum"),
        default="经济舱", comment="舱位",
    )
    depart_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="起飞时间")

    __table_args__ = (Index("idx_flight_order_id", "order_id"),)


class BookingHotel(Base):
    """酒店预订明细表"""
    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    hotel_id: Mapped[Optional[str]] = mapped_column(String(50), comment="酒店ID")
    check_in: Mapped[Optional[datetime]] = mapped_column(Date, comment="入住日期")
    check_out: Mapped[Optional[datetime]] = mapped_column(Date, comment="离店日期")
    room_count: Mapped[int] = mapped_column(Integer, default=1, comment="房间数")
    is_refundable: Mapped[int] = mapped_column(Integer, default=1, comment="是否可免费取消 1/0")

    __table_args__ = (Index("idx_hotel_order_id", "order_id"),)


# ============================================================
# 扩展黑名单
# ============================================================

class BlacklistExtra(Base):
    """扩展黑名单表 (旅游行业: 护照/证件/设备指纹/支付账号)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    type: Mapped[str] = mapped_column(
        Enum("护照号", "证件号", "设备指纹", "支付账号", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="创建时间")

    __table_args__ = (Index("idx_blacklist_extra_type_value", "type", "value"),)