"""教育行业风控系统的业务表 ORM。

这 7 张表只描述教育业务实体，供业务校验、特征工程和规则引擎查询；
风控核心表仍由 :mod:`app.models_risk` 提供，不在这里重复定义或修改。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserInfo(Base):
    """学生、家长和老师共用的账号档案。"""

    __tablename__ = "user_info"
    __table_args__ = (
        Index("idx_user_role_active", "role", "is_active"),
        Index("idx_user_device", "device_id"),
        Index("idx_user_id_card_hash", "id_card_hash"),
        {"comment": "教育平台用户信息"},
    )

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="用户姓名")
    role: Mapped[str] = mapped_column(
        Enum("学生", "家长", "老师", name="education_user_role_enum"),
        nullable=False,
        comment="用户角色",
    )
    student_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, comment="学号/学员编号（非学生可为空）"
    )
    id_card_hash: Mapped[Optional[str]] = mapped_column(
        String(64), comment="身份证号SHA-256哈希，不保存明文"
    )
    real_name_status: Mapped[str] = mapped_column(
        Enum("未认证", "已认证", "认证失败", name="real_name_status_enum"),
        nullable=False,
        default="未认证",
        server_default="未认证",
        comment="实名认证状态",
    )
    guardian_consent_status: Mapped[str] = mapped_column(
        Enum("不适用", "待确认", "已同意", "已撤回", name="guardian_consent_status_enum"),
        nullable=False,
        default="不适用",
        server_default="不适用",
        comment="未成年人监护人同意状态",
    )
    register_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="注册时间"
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="注册/常用设备指纹")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="账号是否有效"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=func.now,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    taught_courses: Mapped[list[Course]] = relationship(back_populates="teacher")
    orders: Mapped[list[OrderInfo]] = relationship(back_populates="user")
    learning_progresses: Mapped[list[LearningProgress]] = relationship(back_populates="user")
    live_rewards: Mapped[list[LiveReward]] = relationship(
        foreign_keys="LiveReward.user_id", back_populates="user"
    )


class Course(Base):
    """平台课程档案。"""

    __tablename__ = "course"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_course_price_non_negative"),
        CheckConstraint("total_hours > 0", name="ck_course_total_hours_positive"),
        Index("idx_course_category_status", "category", "status"),
        Index("idx_course_teacher", "teacher_id"),
        {"comment": "教育课程信息"},
    )

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    name: Mapped[str] = mapped_column(String(150), nullable=False, comment="课程名称")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程分类")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="课程标准价格")
    teacher_id: Mapped[str] = mapped_column(
        ForeignKey("user_info.user_id", ondelete="RESTRICT"), nullable=False, comment="授课老师ID"
    )
    total_hours: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, comment="课程总学时"
    )
    target_role: Mapped[str] = mapped_column(
        Enum("学生", "家长", "老师", "不限", name="course_target_role_enum"),
        nullable=False,
        default="学生",
        server_default="学生",
        comment="课程适用角色",
    )
    status: Mapped[str] = mapped_column(
        Enum("草稿", "上架", "下架", name="course_status_enum"),
        nullable=False,
        default="草稿",
        server_default="草稿",
        comment="课程状态",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="创建时间"
    )

    teacher: Mapped[UserInfo] = relationship(back_populates="taught_courses")
    orders: Mapped[list[OrderInfo]] = relationship(back_populates="course")
    learning_progresses: Mapped[list[LearningProgress]] = relationship(back_populates="course")


class OrderInfo(Base):
    """课程报名订单；沿用 ``order_info`` 表名以兼容风控流水线抽象。"""

    __tablename__ = "order_info"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_order_total_amount_non_negative"),
        CheckConstraint("discount_amount >= 0", name="ck_order_discount_non_negative"),
        CheckConstraint("discount_amount <= total_amount", name="ck_order_discount_not_exceed_total"),
        CheckConstraint("expected_finish_days > 0", name="ck_order_finish_days_positive"),
        Index("idx_order_user_time", "user_id", "order_time"),
        Index("idx_order_course_time", "course_id", "order_time"),
        Index("idx_order_status_time", "status", "order_time"),
        {"comment": "课程报名订单"},
    )

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="报名订单ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_info.user_id", ondelete="RESTRICT"), nullable=False, comment="报名用户ID"
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("course.course_id", ondelete="RESTRICT"), nullable=False, comment="课程ID"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="订单原始金额"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0", comment="优惠金额"
    )
    study_goal: Mapped[Optional[str]] = mapped_column(String(255), comment="学习目标")
    expected_finish_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90", comment="预计完成天数"
    )
    status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "已取消", "部分退费", "已退费", name="education_order_status_enum"),
        nullable=False,
        default="待支付",
        server_default="待支付",
        comment="订单状态",
    )
    order_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="下单时间"
    )
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")
    pay_channel: Mapped[Optional[str]] = mapped_column(String(30), comment="支付渠道")
    payment_account_hash: Mapped[Optional[str]] = mapped_column(
        String(64), comment="支付账号哈希"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="创建时间"
    )

    user: Mapped[UserInfo] = relationship(back_populates="orders")
    course: Mapped[Course] = relationship(back_populates="orders")
    learning_progress: Mapped[Optional[LearningProgress]] = relationship(
        back_populates="order", uselist=False
    )
    refund_requests: Mapped[list[RefundRequest]] = relationship(back_populates="order")


class LearningProgress(Base):
    """用户在一笔课程订单上的学习进度。"""

    __tablename__ = "learning_progress"
    __table_args__ = (
        UniqueConstraint("order_id", name="uk_progress_order"),
        CheckConstraint("total_minutes >= 0", name="ck_progress_minutes_non_negative"),
        CheckConstraint(
            "completion_rate >= 0 AND completion_rate <= 100",
            name="ck_progress_completion_rate_range",
        ),
        Index("idx_progress_user_active", "user_id", "last_active_at"),
        Index("idx_progress_course", "course_id"),
        Index("idx_progress_device", "device_id"),
        {"comment": "课程学习进度"},
    )

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="学习进度ID")
    order_id: Mapped[str] = mapped_column(
        ForeignKey("order_info.order_id", ondelete="CASCADE"), nullable=False, comment="报名订单ID"
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_info.user_id", ondelete="RESTRICT"), nullable=False, comment="用户ID"
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("course.course_id", ondelete="RESTRICT"), nullable=False, comment="课程ID"
    )
    total_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="累计学习分钟数"
    )
    completion_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default="0", comment="完成率(0-100)"
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最后学习时间")
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="最近学习设备指纹")
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=func.now,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    order: Mapped[OrderInfo] = relationship(back_populates="learning_progress")
    user: Mapped[UserInfo] = relationship(back_populates="learning_progresses")
    course: Mapped[Course] = relationship(back_populates="learning_progresses")


class RefundRequest(Base):
    """课程退费申请及申请时学习快照。"""

    __tablename__ = "refund_request"
    __table_args__ = (
        CheckConstraint("refund_amount >= 0", name="ck_refund_amount_non_negative"),
        CheckConstraint(
            "study_minutes_before_refund >= 0", name="ck_refund_study_minutes_non_negative"
        ),
        Index("idx_refund_order_time", "order_id", "apply_time"),
        Index("idx_refund_status_time", "status", "apply_time"),
        Index("idx_refund_account", "refund_account_hash"),
        {"comment": "课程退费申请"},
    )

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退费申请ID")
    order_id: Mapped[str] = mapped_column(
        ForeignKey("order_info.order_id", ondelete="RESTRICT"), nullable=False, comment="报名订单ID"
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment="退费原因")
    study_minutes_before_refund: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="退费申请时已学分钟数"
    )
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="申请退费金额"
    )
    status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过", "已拒绝", "已退款", name="refund_status_enum"),
        nullable=False,
        default="待审核",
        server_default="待审核",
        comment="退费状态",
    )
    refund_account_hash: Mapped[Optional[str]] = mapped_column(
        String(64), comment="退款目标账号哈希"
    )
    is_original_route: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="是否原路退回"
    )
    apply_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="申请时间"
    )
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")

    order: Mapped[OrderInfo] = relationship(back_populates="refund_requests")


class LiveReward(Base):
    """直播课堂打赏/互动消费记录。"""

    __tablename__ = "live_reward"
    __table_args__ = (
        CheckConstraint("reward_amount > 0", name="ck_reward_amount_positive"),
        Index("idx_reward_user_time", "user_id", "reward_time"),
        Index("idx_reward_session_time", "live_session_id", "reward_time"),
        Index("idx_reward_device", "device_id"),
        Index("idx_reward_teacher", "teacher_id"),
        {"comment": "直播课堂打赏记录"},
    )

    reward_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="打赏记录ID")
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_info.user_id", ondelete="RESTRICT"), nullable=False, comment="打赏用户ID"
    )
    teacher_id: Mapped[str] = mapped_column(
        ForeignKey("user_info.user_id", ondelete="RESTRICT"), nullable=False, comment="收款老师ID"
    )
    live_session_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="直播场次ID")
    reward_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="打赏金额"
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(64), comment="打赏设备指纹")
    guardian_consent_snapshot: Mapped[str] = mapped_column(
        Enum("不适用", "待确认", "已同意", "已撤回", name="reward_guardian_consent_enum"),
        nullable=False,
        default="不适用",
        server_default="不适用",
        comment="打赏时监护人同意状态快照",
    )
    payment_account_hash: Mapped[Optional[str]] = mapped_column(
        String(64), comment="支付账号哈希"
    )
    status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "已拦截", "已退款", name="reward_status_enum"),
        nullable=False,
        default="待支付",
        server_default="待支付",
        comment="打赏状态",
    )
    reward_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="打赏时间"
    )

    user: Mapped[UserInfo] = relationship(
        foreign_keys=[user_id], back_populates="live_rewards"
    )
    teacher: Mapped[UserInfo] = relationship(foreign_keys=[teacher_id])


class BlacklistExtra(Base):
    """教育行业特有标识的补充黑名单。

    通用用户黑名单仍使用受保护的 ``risk_blacklist``；本表保存学号、
    证件哈希、设备指纹和直播账号等教育业务标识。
    """

    __tablename__ = "blacklist_extra"
    __table_args__ = (
        UniqueConstraint("entry_type", "entry_value", name="uk_blacklist_extra_type_value"),
        Index("idx_blacklist_extra_expire", "expire_at"),
        {"comment": "教育业务补充黑名单"},
    )

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="条目ID")
    entry_type: Mapped[str] = mapped_column(
        Enum("学号", "身份证哈希", "设备指纹", "直播账号", name="education_blacklist_type_enum"),
        nullable=False,
        comment="黑名单标识类型",
    )
    entry_value: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="标识值；敏感标识只保存哈希"
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间，空值表示永久")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="是否有效"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now, server_default=func.now(), comment="创建时间"
    )


BUSINESS_MODELS = (
    UserInfo,
    Course,
    OrderInfo,
    LearningProgress,
    RefundRequest,
    LiveReward,
    BlacklistExtra,
)


__all__ = [model.__name__ for model in BUSINESS_MODELS] + ["BUSINESS_MODELS"]
