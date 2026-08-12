"""
旅游风控系统 - 业务表 ORM (8 张)
只读映射 OTA 平台业务实体 (用户/订单/乘客/签证/酒店/航班/退改/扩展黑名单)
不参与风控决策本身, 但被特征工程和规则引擎查询

设计说明 (对应任务书场景 A):
  - UserInfo         加实名状态 / VIP / 账号年龄 (旅游必须)
  - OrderInfo        加目的地国家 / 出行日期 / 乘客数
  - PassengerInfo    1 个订单 N 个乘客 (对应电商 ReceiveInfo 的"收货人"位置)
  - VisaApplication  电商没有"签证"概念, 全新表
  - BookingHotel     全新表
  - BookingFlight    全新表
  - OrderRefund      退改单 (事件"退改申请"的校验实体, 第 8 张表)
  - BlacklistExtra   业务侧黑名单台账, type 含 护照号/签证号/设备指纹
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与订单基础
# ============================================================

class UserInfo(Base):
    """旅游用户信息表 (实名状态 / VIP / 账号年龄是旅游风控的关键)"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    real_name_status: Mapped[int] = mapped_column(
        Integer, default=0, comment="实名状态 0=未实名 1=已实名",
    )
    vip_level: Mapped[int] = mapped_column(Integer, default=0, comment="VIP等级 0-4")
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, comment="账号年龄(天)")
    register_time: Mapped[datetime] = mapped_column(DateTime, comment="注册时间")


class OrderInfo(Base):
    """旅游订单表 (目的地国家 / 出行日期 / 乘客数是旅游差异字段)"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    order_type: Mapped[str] = mapped_column(
        Enum("机票", "酒店", "签证", "跟团游", name="order_type_enum"),
        nullable=False, comment="订单类型",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单金额")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家")
    depart_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="出发日期")
    return_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="返程日期")
    passenger_count: Mapped[int] = mapped_column(Integer, default=1, comment="乘客数")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="下单时间")
    order_status: Mapped[str] = mapped_column(
        Enum("已支付", "已完成", "已取消", "已退改", name="order_status_enum"),
        nullable=False, default="已支付", comment="订单状态",
    )


# ============================================================
# 乘客域 (1 订单 N 乘客)
# ============================================================

class PassengerInfo(Base):
    """乘客信息表 (证件号用于黑护照 / 一致性校验)"""
    __tablename__ = "passenger_info"

    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="乘客ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", "港澳通行证", "台胞证", name="id_type_enum"),
        nullable=False, default="身份证", comment="证件类型",
    )
    id_number: Mapped[str] = mapped_column(String(50), nullable=False, comment="证件号")
    nationality: Mapped[str] = mapped_column(String(50), nullable=False, comment="国籍")
    age: Mapped[int] = mapped_column(Integer, default=0, comment="年龄")


# ============================================================
# 签证域
# ============================================================

class VisaApplication(Base):
    """签证申请表 (拒签历史是旅游风控核心信号)"""
    __tablename__ = "visa_application"

    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="签证申请ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False, comment="目的地国家")
    visa_type: Mapped[str] = mapped_column(
        Enum("旅游签证", "商务签证", "留学签证", "探亲签证", name="visa_type_enum"),
        nullable=False, default="旅游签证", comment="签证类型",
    )
    reject_history: Mapped[int] = mapped_column(Integer, default=0, comment="历史拒签次数")
    submit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="提交时间")


# ============================================================
# 酒店 / 航班预订域
# ============================================================

class BookingHotel(Base):
    """酒店预订表"""
    __tablename__ = "booking_hotel"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="酒店预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="酒店ID")
    check_in: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="入住时间")
    check_out: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="离店时间")
    room_count: Mapped[int] = mapped_column(Integer, default=1, comment="房间数")
    is_refundable: Mapped[int] = mapped_column(Integer, default=1, comment="是否可退 1=可退 0=不可退")


class BookingFlight(Base):
    """机票预订表 (同航班高频预订是黄牛囤票信号)"""
    __tablename__ = "booking_flight"

    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机票预订ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="航班号")
    depart_airport: Mapped[str] = mapped_column(String(50), nullable=False, comment="出发机场")
    arrive_airport: Mapped[str] = mapped_column(String(50), nullable=False, comment="到达机场")
    cabin_class: Mapped[str] = mapped_column(
        Enum("经济舱", "商务舱", "头等舱", name="cabin_class_enum"),
        nullable=False, default="经济舱", comment="舱位",
    )


# ============================================================
# 退改域 (第 8 张表: "退改申请"事件的事件校验实体)
# ============================================================

class OrderRefund(Base):
    """退改申请表 (对应电商 Postsale 的"售后"位置)"""
    __tablename__ = "order_refund"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退改单ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="退改金额")
    refund_type: Mapped[str] = mapped_column(
        Enum("退款", "改期", "换乘客", name="refund_type_enum"),
        nullable=False, default="退款", comment="退改类型",
    )
    refund_status: Mapped[str] = mapped_column(
        Enum("处理中", "已完成", "已驳回", name="refund_status_enum"),
        nullable=False, default="处理中", comment="退改状态",
    )
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")


# ============================================================
# 业务侧黑名单台账 (决策权威是 risk_blacklist, 本表是镜像)
# ============================================================

class BlacklistExtra(Base):
    """业务黑名单台账表 (type: 护照号/签证号/设备指纹, 由写黑名单的入口同步镜像)"""
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="条目ID")
    type: Mapped[str] = mapped_column(
        Enum("护照号", "签证号", "设备指纹", name="blacklist_extra_type_enum"),
        nullable=False, comment="黑名单类型",
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(String(500), comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="软删除时间(NULL=未删)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间",
    )
