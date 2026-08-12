"""
旅游行业风控系统 - 业务表 ORM (7 张)

对应任务书"场景 A: 旅游风控"的 A.1 必有的 7 张业务表:
  - UserInfo          用户信息 (实名状态 / 会员等级 / 注册时长)
  - OrderInfo         订单主表 (机票 / 酒店 / 签证 / 跟团游)
  - PassengerInfo     乘客信息 (1 个订单 N 个乘客, 证件号用于黑名单比对)
  - VisaApplication   签证申请 (拒签历史 / 短期多国申请)
  - BookingHotel      酒店预订明细
  - BookingFlight     机票预订明细
  - BlacklistExtra    业务黑名单扩展表 (设备指纹 / IP / 护照号 / 签证号 / 身份证号)

风控核心 9 张表 (app/models_risk.py) 完全复用, 不改 schema.
索引设计原则: 特征计算的高频查询 (按 user / order / 证件号 / 时间) 全部走索引.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户域
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    real_name_status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, comment="实名状态(0=未实名,1=已实名)",
    )
    vip_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="普通", comment="会员等级(普通/银卡/金卡/铂金/钻石)",
    )
    account_age_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="注册时长(天), 新用户大单特征直接取数",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="注册时间",
    )

    __table_args__ = (
        Index("idx_user_account_age", "account_age_days"),
    )


# ============================================================
# 订单域
# ============================================================

class OrderInfo(Base):
    """订单主表 (机票 / 酒店 / 签证 / 跟团游)"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="下单用户ID",
    )
    order_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="订单类型(机票/酒店/签证/跟团游)",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="订单金额(元)",
    )
    dest_country: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="目的地国家",
    )
    depart_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出发日期")
    return_date: Mapped[Optional[date]] = mapped_column(Date, comment="返回日期")
    passenger_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="乘客数",
    )
    order_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="待支付",
        comment="订单状态(待支付/已支付/已出票/已出行/已完成/已取消/已退改)",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="下单时间",
    )
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")

    __table_args__ = (
        Index("idx_order_user_id", "user_id"),
        Index("idx_order_create_time", "create_time"),
        Index("idx_order_type", "order_type"),
        Index("idx_order_depart_date", "depart_date"),
        Index("idx_order_dest_country", "dest_country"),
    )


class PassengerInfo(Base):
    """乘客信息表 (1 个订单对应 N 个乘客, 对应电商版 ReceiveInfo 的层级)"""
    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="乘客ID")
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("order_info.order_id"), nullable=False, comment="所属订单ID",
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="乘客姓名")
    id_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="身份证",
        comment="证件类型(身份证/护照/港澳通行证/台湾通行证/其他)",
    )
    id_number: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="证件号(身份证号/护照号, 黑名单比对目标)",
    )
    nationality: Mapped[str] = mapped_column(
        String(50), nullable=False, default="中国", comment="国籍",
    )
    age: Mapped[int] = mapped_column(Integer, nullable=False, comment="年龄")

    __table_args__ = (
        Index("idx_passenger_order_id", "order_id"),
        Index("idx_passenger_id_number", "id_number"),
    )


class VisaApplication(Base):
    """签证申请表 (电商版没有"签证"概念, 全新表)"""
    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="申请用户ID",
    )
    dest_country: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="目的地国家",
    )
    visa_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="签证类型(旅游/商务/探亲/留学等)",
    )
    reject_history: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="历史拒签次数",
    )
    submit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="提交时间")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="待审核", comment="状态(待审核/通过/拒签)",
    )

    __table_args__ = (
        Index("idx_visa_user_id", "user_id"),
        Index("idx_visa_dest_country", "dest_country"),
        Index("idx_visa_submit_time", "submit_time"),
    )


# ============================================================
# 资源预订明细域 (跟电商版完全不同的全新表)
# ============================================================

class BookingHotel(Base):
    """酒店预订明细表"""
    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("order_info.order_id"), nullable=False, comment="所属订单ID",
    )
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    check_in: Mapped[date] = mapped_column(Date, nullable=False, comment="入住日期")
    check_out: Mapped[date] = mapped_column(Date, nullable=False, comment="离店日期")
    room_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="房间数")
    is_refundable: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, comment="是否可免费取消(0=否,1=是)",
    )

    __table_args__ = (
        Index("idx_hotel_order_id", "order_id"),
        Index("idx_hotel_check_in", "check_in"),
    )


class BookingFlight(Base):
    """机票预订明细表"""
    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机票预订ID")
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("order_info.order_id"), nullable=False, comment="所属订单ID",
    )
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="航班号")
    depart_airport: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="出发机场",
    )
    arrive_airport: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="到达机场",
    )
    cabin_class: Mapped[str] = mapped_column(
        String(20), nullable=False, default="经济舱",
        comment="舱位等级(经济舱/公务舱/头等舱)",
    )

    __table_args__ = (
        Index("idx_flight_order_id", "order_id"),
        Index("idx_flight_no", "flight_no"),
    )


# ============================================================
# 业务黑名单扩展
# ============================================================

class BlacklistExtra(Base):
    """业务黑名单扩展表 (与风控核心 risk_blacklist 互补, 记录业务侧证据)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID",
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="黑名单类型(设备指纹/IP/护照号/签证号/身份证号)",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")

    __table_args__ = (
        UniqueConstraint("type", "value", name="uk_blacklist_extra_type_value"),
        Index("idx_blacklist_extra_type", "type"),
    )
