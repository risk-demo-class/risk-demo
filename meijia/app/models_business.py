"""教育行业业务表 ORM；字段与 docs/字段设计.md 对齐。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import INTEGER, SMALLINT, VARBINARY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(3), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(3), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserInfo(TimestampMixin, Base):
    __tablename__ = "user_info"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    student_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    real_name_status: Mapped[str] = mapped_column(String(20), default="未认证", nullable=False)
    register_at: Mapped[datetime] = mapped_column(DateTime(3), nullable=False, index=True)
    __table_args__ = (
        CheckConstraint("role IN ('学生','家长','老师')", name="chk_user_role"),
        CheckConstraint(
            "real_name_status IN ('未认证','认证中','已认证','认证失败')",
            name="chk_real_name_status",
        ),
    )


class UserDevice(Base):
    __tablename__ = "user_device"
    relation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(3), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "device_fingerprint", name="uk_user_device"),
        Index("idx_device_active", "device_fingerprint", "last_seen_at", "user_id"),
        Index("idx_user_device_active", "user_id", "last_seen_at"),
        CheckConstraint("last_seen_at >= first_seen_at", name="chk_device_seen_time"),
    )


class Course(TimestampMixin, Base):
    __tablename__ = "course"
    course_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    total_hours: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    course_status: Mapped[str] = mapped_column(String(20), default="草稿", nullable=False)
    __table_args__ = (
        Index("idx_course_teacher", "teacher_id"),
        Index("idx_course_category_status", "category", "course_status"),
        CheckConstraint("price >= 0", name="chk_course_price"),
        CheckConstraint("total_hours > 0", name="chk_course_total_hours"),
        CheckConstraint("course_status IN ('草稿','已上架','已下架','已归档')", name="chk_course_status"),
    )


class OrderInfo(TimestampMixin, Base):
    __tablename__ = "order_info"
    order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    learner_user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.course_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    study_goal: Mapped[str | None] = mapped_column(String(500))
    expected_finish_days: Mapped[int | None] = mapped_column(SMALLINT(unsigned=True))
    payment_account_hash: Mapped[str | None] = mapped_column(String(64))
    order_status: Mapped[str] = mapped_column(String(20), default="待支付", nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    __table_args__ = (
        Index("idx_order_user_paid", "user_id", "order_status", "paid_at"),
        Index("idx_order_course_created", "course_id", "order_status", "created_at", "learner_user_id"),
        Index("idx_order_payment_course", "payment_account_hash", "course_id", "created_at"),
        Index("idx_order_learner", "learner_user_id", "course_id"),
        CheckConstraint("total_amount >= 0", name="chk_order_amount"),
        CheckConstraint("expected_finish_days IS NULL OR expected_finish_days > 0", name="chk_order_days"),
        CheckConstraint("order_status IN ('待支付','已支付','已取消','已关闭','部分退款','已退款')", name="chk_order_status"),
    )


class LearningProgress(TimestampMixin, Base):
    __tablename__ = "learning_progress"
    progress_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.course_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    total_minutes: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uk_progress_user_course"),
        Index("idx_progress_course_active", "course_id", "last_active_at", "user_id"),
        CheckConstraint("completion_rate BETWEEN 0 AND 100", name="chk_progress_rate"),
    )


class RefundRequest(TimestampMixin, Base):
    __tablename__ = "refund_request"
    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("order_info.order_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    study_minutes_before_refund: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    refund_status: Mapped[str] = mapped_column(String(20), default="待审核", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(3), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    __table_args__ = (
        Index("idx_refund_order_requested", "order_id", "requested_at"),
        Index("idx_refund_status_completed", "refund_status", "completed_at", "order_id"),
        Index("idx_refund_requester", "requested_by_user_id", "requested_at"),
        CheckConstraint("requested_amount > 0", name="chk_refund_requested_amount"),
        CheckConstraint("refund_amount IS NULL OR (refund_amount >= 0 AND refund_amount <= requested_amount)", name="chk_refund_amount"),
        CheckConstraint("refund_status IN ('待审核','审核中','已批准','已拒绝','已取消','退款成功','退款失败')", name="chk_refund_status"),
    )


class BlacklistExtra(TimestampMixin, Base):
    __tablename__ = "blacklist_extra"
    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    value_masked: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="启用", nullable=False)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    created_by: Mapped[str] = mapped_column(String(50), default="system", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    __table_args__ = (
        UniqueConstraint("type", "value", name="uk_blacklist_type_value"),
        Index("idx_blacklist_active", "status", "expire_at", "deleted_at"),
        CheckConstraint("type IN ('用户ID','学号','身份证','设备指纹','直播账号')", name="chk_blacklist_type"),
        CheckConstraint("status IN ('启用','停用')", name="chk_blacklist_status"),
    )


class EducationCredential(TimestampMixin, Base):
    __tablename__ = "education_credential"
    credential_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    id_card_ciphertext: Mapped[bytes] = mapped_column(VARBINARY(512), nullable=False)
    id_card_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    id_card_masked: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_education_level: Mapped[str] = mapped_column(String(30), nullable=False)
    authoritative_education_level: Mapped[str | None] = mapped_column(String(30))
    verify_status: Mapped[str] = mapped_column(String(20), default="待核验", nullable=False)
    mismatch_reason: Mapped[str | None] = mapped_column(String(100))
    verify_source: Mapped[str | None] = mapped_column(String(50))
    verify_reference_id: Mapped[str | None] = mapped_column(String(100))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(3), server_default=func.now(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(3))
    __table_args__ = (
        Index("idx_credential_user_submitted", "user_id", "submitted_at"),
        Index("idx_credential_status", "verify_status", "verified_at"),
        CheckConstraint("verify_status IN ('待核验','匹配','不匹配','无记录','系统异常')", name="chk_credential_status"),
    )


class LiveReward(TimestampMixin, Base):
    __tablename__ = "live_reward"
    reward_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    live_session_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_info.user_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    reward_account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    original_reward_id: Mapped[str | None] = mapped_column(ForeignKey("live_reward.reward_id", ondelete="RESTRICT", onupdate="CASCADE"))
    transaction_type: Mapped[str] = mapped_column(String(20), default="打赏", nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reward_status: Mapped[str] = mapped_column(String(20), default="处理中", nullable=False)
    rewarded_at: Mapped[datetime] = mapped_column(DateTime(3), server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("idx_reward_account_session", "reward_account_id", "live_session_id", "reward_status", "transaction_type", "rewarded_at"),
        Index("idx_reward_user_time", "user_id", "rewarded_at"),
        Index("idx_reward_original", "original_reward_id"),
        CheckConstraint("transaction_type IN ('打赏','退款','撤销','冲正')", name="chk_reward_type"),
        CheckConstraint("reward_status IN ('处理中','成功','失败')", name="chk_reward_status"),
        CheckConstraint("amount > 0", name="chk_reward_amount"),
    )
