"""在线教育平台业务 ORM。

业务层只保留 6 张表：用户、课程、课程订单、学习进度、退费申请和教育扩展黑名单。
风控核心表由 ``models_risk.py`` 继续管理。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
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
    """学员、家长和教师的统一用户档案。"""

    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="姓名")
    role: Mapped[str] = mapped_column(
        Enum("student", "parent", "teacher", name="education_user_role_enum"),
        nullable=False,
        default="student",
        comment="用户角色",
    )
    student_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, comment="学号")
    id_card_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, comment="身份证SHA-256")
    real_name_status: Mapped[str] = mapped_column(
        Enum("UNVERIFIED", "VERIFIED", "REJECTED", name="real_name_status_enum"),
        nullable=False,
        default="UNVERIFIED",
        comment="实名认证状态",
    )
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    device_id: Mapped[Optional[str]] = mapped_column(String(100), comment="主要设备标识")

    __table_args__ = (
        Index("idx_user_role", "role"),
        Index("idx_user_device_id", "device_id"),
        Index("idx_user_register_at", "register_at"),
    )


class Course(Base):
    """课程主档。"""

    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="课程名称")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程分类")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="课程价格")
    teacher_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False, comment="总课时")
    audience_role: Mapped[str] = mapped_column(
        Enum("student", "all", name="course_audience_role_enum"),
        nullable=False,
        default="student",
        comment="适用人群",
    )
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "INACTIVE", name="course_status_enum"),
        nullable=False,
        default="ACTIVE",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_course_category", "category"),
        Index("idx_course_teacher", "teacher_id"),
        CheckConstraint("price >= 0", name="ck_course_price"),
        CheckConstraint("total_hours > 0", name="ck_course_total_hours"),
    )


class OrderInfo(Base):
    """课程报名/购买订单，一张订单对应一门课程。"""

    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程订单ID")
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.course_id"), nullable=False)
    order_type: Mapped[str] = mapped_column(
        Enum("ENROLLMENT", "PURCHASE", name="education_order_type_enum"),
        nullable=False,
        default="PURCHASE",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_status: Mapped[str] = mapped_column(
        Enum("PENDING", "PAID", "CANCELLED", "REFUNDED", name="education_payment_status_enum"),
        nullable=False,
        default="PAID",
    )
    study_goal: Mapped[Optional[str]] = mapped_column(String(200))
    expected_finish_days: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_order_user_time", "user_id", "created_at"),
        Index("idx_order_course_time", "course_id", "created_at"),
        CheckConstraint("total_amount >= 0", name="ck_order_total_amount"),
        CheckConstraint(
            "expected_finish_days IS NULL OR expected_finish_days > 0",
            name="ck_order_expected_finish_days",
        ),
    )


class LearningProgress(Base):
    """课程学习进度与活跃事实。"""

    __tablename__ = "learning_progress"

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.course_id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("order_info.order_id"), nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_progress_user_course"),
        Index("idx_progress_user_active", "user_id", "last_active_at"),
        Index("idx_progress_order", "order_id"),
        CheckConstraint("total_minutes >= 0", name="ck_progress_minutes"),
        CheckConstraint("completion_rate >= 0 AND completion_rate <= 1", name="ck_progress_rate"),
    )


class RefundRequest(Base):
    """课程退费申请。"""

    __tablename__ = "refund_request"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("order_info.order_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    study_minutes_before_refund: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("PENDING", "APPROVED", "REJECTED", name="refund_status_enum"),
        nullable=False,
        default="PENDING",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_refund_user_time", "user_id", "created_at"),
        Index("idx_refund_order", "order_id"),
        CheckConstraint("study_minutes_before_refund >= 0", name="ck_refund_study_minutes"),
        CheckConstraint("refund_amount >= 0", name="ck_refund_amount"),
    )


class BlacklistExtra(Base):
    """教育业务专用黑名单，用于学号、身份证、设备和直播账号。"""

    __tablename__ = "blacklist_extra"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(
        Enum("student_id", "id_card", "device_id", "live_account", name="education_blacklist_type_enum"),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "REMOVED", name="education_blacklist_status_enum"),
        nullable=False,
        default="ACTIVE",
    )
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_blacklist_extra_type_value"),
        Index("idx_blacklist_extra_active", "status", "expire_at"),
    )


BUSINESS_MODELS = (
    UserInfo,
    Course,
    OrderInfo,
    LearningProgress,
    RefundRequest,
    BlacklistExtra,
)
