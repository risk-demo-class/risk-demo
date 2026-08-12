"""在线教育风控的 6 张业务表。

这些表保存业务事实；risk_* 表仍保存风控判断过程，二者分离。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    __tablename__ = "user_info"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, comment="学生/家长/老师")
    student_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)
    real_name_status: Mapped[int] = mapped_column(Integer, default=1)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Course(Base):
    __tablename__ = "course"
    course_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    teacher_id: Mapped[str] = mapped_column(String(50), nullable=False)
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False)


class Enrollment(Base):
    __tablename__ = "enrollment"
    enrollment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(String(50), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="已报名")
    study_goal: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class LearningProgress(Base):
    __tablename__ = "learning_progress"
    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(String(50), nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, default=0)
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RefundRequest(Base):
    __tablename__ = "refund_request"
    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    study_minutes_before_refund: Mapped[int] = mapped_column(Integer, default=0)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    request_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="待审核")


class LiveReward(Base):
    __tablename__ = "live_reward"
    reward_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    teacher_id: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reward_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    live_room_id: Mapped[str] = mapped_column(String(50), nullable=False)
