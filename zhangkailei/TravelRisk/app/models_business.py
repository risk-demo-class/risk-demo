"""TravelRisk 旅游行业业务表 ORM（9 张）。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TravelUser(Base):
    __tablename__ = "travel_user"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    real_name_status: Mapped[int] = mapped_column(Integer, default=0)
    vip_level: Mapped[int] = mapped_column(Integer, default=0)
    account_status: Mapped[str] = mapped_column(String(20), default="正常")
    register_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class TravelOrder(Base):
    __tablename__ = "travel_order"
    order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("travel_user.user_id"), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False)
    depart_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    passenger_count: Mapped[int] = mapped_column(Integer, default=1)
    order_status: Mapped[str] = mapped_column(String(20), default="待支付", index=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class PassengerInfo(Base):
    __tablename__ = "passenger_info"
    passenger_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("travel_user.user_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    id_type: Mapped[str] = mapped_column(String(20), nullable=False)
    id_number_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    nationality: Mapped[str] = mapped_column(String(50), default="中国")
    birthday: Mapped[Optional[date]] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("user_id", "id_number_hash", name="uq_user_identity"),)


class OrderPassenger(Base):
    __tablename__ = "order_passenger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("travel_order.order_id"), nullable=False, index=True)
    passenger_id: Mapped[str] = mapped_column(ForeignKey("passenger_info.passenger_id"), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("order_id", "passenger_id", name="uq_order_passenger"),)


class VisaApplication(Base):
    __tablename__ = "visa_application"
    visa_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("travel_order.order_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("travel_user.user_id"), nullable=False, index=True)
    dest_country: Mapped[str] = mapped_column(String(50), nullable=False)
    visa_type: Mapped[str] = mapped_column(String(30), nullable=False)
    application_status: Mapped[str] = mapped_column(String(20), default="待审核", index=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500))
    submit_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class FlightBooking(Base):
    __tablename__ = "flight_booking"
    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("travel_order.order_id"), nullable=False, unique=True, index=True)
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    depart_airport: Mapped[str] = mapped_column(String(20), nullable=False)
    arrive_airport: Mapped[str] = mapped_column(String(20), nullable=False)
    cabin_class: Mapped[str] = mapped_column(String(20), default="经济舱")
    depart_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ticket_count: Mapped[int] = mapped_column(Integer, default=1)


class HotelBooking(Base):
    __tablename__ = "hotel_booking"
    booking_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("travel_order.order_id"), nullable=False, unique=True, index=True)
    hotel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    room_count: Mapped[int] = mapped_column(Integer, default=1)
    is_refundable: Mapped[int] = mapped_column(Integer, default=1)


class PaymentRecord(Base):
    __tablename__ = "payment_record"
    payment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("travel_order.order_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("travel_user.user_id"), nullable=False, index=True)
    payment_account_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="成功")
    payment_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class TravelBlacklistEntry(Base):
    __tablename__ = "travel_blacklist_entry"
    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_value_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=datetime.now)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("entry_type", "entry_value_hash", name="uq_travel_blacklist_value"),
        Index("idx_travel_blacklist_active", "entry_type", "deleted_at", "expire_time"),
    )
