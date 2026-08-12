"""Model 层：在线教育业务实体。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Student(Base):
    __tablename__ = "student"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name_masked: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="学生")
    student_id_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    real_name_status: Mapped[str] = mapped_column(String(20), nullable=False, default="未认证")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Course(Base):
    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    teacher_id: Mapped[str | None] = mapped_column(String(50))
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False)


class Enrollment(Base):
    __tablename__ = "enrollment"

    enrollment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("student.user_id"), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.course_id"), nullable=False, index=True)
    paid_amount: Mapped[float] = mapped_column(Float, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    enroll_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)
    pay_at: Mapped[datetime | None] = mapped_column(DateTime)
    study_goal: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="已报名")


class LearningProgress(Base):
    __tablename__ = "learning_progress"

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("student.user_id"), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.course_id"), nullable=False, index=True)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime)


class RefundRequest(Base):
    __tablename__ = "refund_request"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("enrollment.enrollment_id"), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    study_minutes_before_refund: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refund_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="申请中")
    apply_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class CredentialVerification(Base):
    __tablename__ = "credential_verification"

    verification_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("student.user_id"), nullable=False, index=True)
    verification_type: Mapped[str] = mapped_column(String(30), nullable=False)
    id_card_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="待审核")
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    submit_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class DeviceBinding(Base):
    __tablename__ = "device_binding"

    binding_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("student.user_id"), nullable=False, index=True)
    device_fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)
