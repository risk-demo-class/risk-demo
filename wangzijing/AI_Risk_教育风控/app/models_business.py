"""教育行业风控系统的七张业务表 ORM。

业务表负责提供风控所需的事实数据，不在模型层执行风控决策。
学号、身份证、设备指纹和 IP 仅保存不可逆哈希值。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInfo(Base):
    """学员、家长和教师的统一账户表。"""

    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="展示名称")
    role: Mapped[str] = mapped_column(
        Enum("学员", "家长", "教师", name="education_user_role_enum"),
        nullable=False,
        comment="用户角色",
    )
    student_id_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="学号SHA-256哈希"
    )
    id_number_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="身份证号SHA-256哈希"
    )
    real_name_status: Mapped[str] = mapped_column(
        Enum("未认证", "认证中", "已认证", "认证失败", name="real_name_status_enum"),
        nullable=False,
        default="未认证",
        server_default="未认证",
        comment="实名认证状态",
    )
    register_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), comment="注册时间"
    )
    account_status: Mapped[str] = mapped_column(
        Enum("正常", "冻结", "注销", name="education_account_status_enum"),
        nullable=False,
        default="正常",
        server_default="正常",
        comment="账户状态",
    )

    __table_args__ = (
        Index("idx_user_student_hash", "student_id_hash"),
        Index("idx_user_id_number_hash", "id_number_hash"),
        Index("idx_user_register_at", "register_at"),
    )


class Course(Base):
    """课程主数据。"""

    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    course_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="课程名称")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程分类")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="课程原价")
    teacher_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="授课教师ID"
    )
    total_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, comment="课程总课时")
    course_status: Mapped[str] = mapped_column(
        Enum("草稿", "上架", "下架", name="education_course_status_enum"),
        nullable=False,
        default="上架",
        server_default="上架",
        comment="课程状态",
    )

    __table_args__ = (
        Index("idx_course_category_status", "category", "course_status"),
        Index("idx_course_teacher_id", "teacher_id"),
    )


class OrderInfo(Base):
    """课程报名订单；一张订单对应一门课程。"""

    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="报名订单ID")
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="报名用户ID"
    )
    course_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("course.course_id"), nullable=False, comment="课程ID"
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单原金额")
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00", comment="优惠金额"
    )
    final_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实付金额")
    order_status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "已取消", "已退费", name="education_order_status_enum"),
        nullable=False,
        default="待支付",
        server_default="待支付",
        comment="报名订单状态",
    )
    channel: Mapped[str] = mapped_column(
        Enum("网页", "移动端", "线下录入", name="education_order_channel_enum"),
        nullable=False,
        default="网页",
        server_default="网页",
        comment="报名渠道",
    )
    device_id_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="下单设备指纹哈希")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), comment="创建时间"
    )
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")

    __table_args__ = (
        Index("idx_order_user_time", "user_id", "create_time"),
        Index("idx_order_course_id", "course_id"),
        Index("idx_order_device_hash", "device_id_hash"),
        Index("idx_order_status_time", "order_status", "create_time"),
    )


class LearningProgress(Base):
    """报名后的学习进度快照。"""

    __tablename__ = "learning_progress"

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="学习进度ID")
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="学员ID"
    )
    course_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("course.course_id"), nullable=False, comment="课程ID"
    )
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("order_info.order_id"), nullable=False, comment="报名订单ID"
    )
    total_minutes: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00", comment="累计学习分钟"
    )
    completion_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.0000"), server_default="0.0000", comment="完成率[0,1]"
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最后学习时间")

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "order_id", name="uk_progress_user_course_order"),
        Index("idx_progress_order_id", "order_id"),
        Index("idx_progress_user_active", "user_id", "last_active_at"),
    )


class RefundRequest(Base):
    """课程退费申请及处理结果。"""

    __tablename__ = "refund_request"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退费申请ID")
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("order_info.order_id"), nullable=False, comment="报名订单ID"
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="申请用户ID"
    )
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="申请退费金额")
    reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="退费原因")
    refund_status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过", "已拒绝", "已撤销", name="education_refund_status_enum"),
        nullable=False,
        default="待审核",
        server_default="待审核",
        comment="退费状态",
    )
    apply_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), comment="申请时间"
    )
    processed_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="处理时间")

    __table_args__ = (
        Index("idx_refund_user_time", "user_id", "apply_time"),
        Index("idx_refund_order_id", "order_id"),
        Index("idx_refund_status_time", "refund_status", "apply_time"),
    )


class IdentityVerification(Base):
    """实名认证、学籍验证和学历认证记录。"""

    __tablename__ = "identity_verification"

    verify_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="认证记录ID")
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="用户ID"
    )
    verify_type: Mapped[str] = mapped_column(
        Enum("实名认证", "学籍验证", "学历认证", name="education_verify_type_enum"),
        nullable=False,
        comment="认证类型",
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="证件或材料哈希")
    verify_result: Mapped[str] = mapped_column(
        Enum("待审核", "通过", "失败", name="education_verify_result_enum"),
        nullable=False,
        default="待审核",
        server_default="待审核",
        comment="认证结果",
    )
    fail_reason: Mapped[Optional[str]] = mapped_column(String(500), comment="失败原因")
    submit_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), comment="提交时间"
    )
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审核时间")

    __table_args__ = (
        Index("idx_verify_user_time", "user_id", "submit_time"),
        Index("idx_verify_document_hash", "document_hash"),
        Index("idx_verify_result_time", "verify_result", "submit_time"),
    )


class DeviceBinding(Base):
    """账户与设备、IP 的关联事实。"""

    __tablename__ = "device_binding"

    binding_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="绑定记录ID",
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_info.user_id"), nullable=False, comment="用户ID"
    )
    device_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="设备指纹哈希")
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="IP地址哈希")
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), comment="首次出现时间"
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), comment="最近出现时间"
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="是否为当前有效设备"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "device_id_hash", name="uk_device_user_hash"),
        Index("idx_device_hash_current", "device_id_hash", "is_current"),
        Index("idx_device_user_last_seen", "user_id", "last_seen"),
        Index("idx_device_ip_hash", "ip_hash"),
    )
