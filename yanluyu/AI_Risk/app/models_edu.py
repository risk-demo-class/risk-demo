"""
教育风控系统 - 教育业务表 ORM 模型 (SQLAlchemy 2.0)
7 张业务表: UserInfo / Course / OrderInfo / LearningProgress / RefundRequest / BlacklistExtra / DonationRecord
"""
import json
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    DateTime, Enum as SAEnum, Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# ENUM 定义
# ============================================================

class UserRole(str, Enum):
    STUDENT = "学生"
    TEACHER = "老师"
    ADMIN = "管理员"


class RealNameStatus(str, Enum):
    UNCERTIFIED = "未认证"
    CERTIFIED = "已认证"
    FAILED = "认证失败"


class CourseCategory(str, Enum):
    SUBJECT = "学科辅导"
    INTEREST = "兴趣特长"
    VOCATIONAL = "职业技能"
    LANGUAGE = "语言学习"
    EXAM = "考试考证"
    OTHER = "其他"


class CourseTargetAudience(str, Enum):
    STUDENT = "学生"
    GENERAL = "通用"


class OrderStatus(str, Enum):
    PENDING = "待支付"
    PAID = "已支付"
    STUDYING = "学习中"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class RefundStatus(str, Enum):
    PENDING = "待审核"
    APPROVED = "已同意"
    REJECTED = "已拒绝"


class BlacklistExtraType(str, Enum):
    STUDENT_ID = "学号"
    ID_NUMBER = "身份证号"
    PHONE = "手机号"
    DEVICE = "设备指纹"


# ============================================================
# 1. 用户信息表
# ============================================================

class UserInfo(Base):
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名")
    role: Mapped[str] = mapped_column(
        SAEnum("学生", "老师", "管理员"), nullable=False, comment="角色"
    )
    student_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="学号")
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="身份证号")
    real_name_status: Mapped[str] = mapped_column(
        SAEnum("未认证", "已认证", "认证失败"), nullable=False, default="未认证", comment="实名认证状态"
    )
    register_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="注册时间"
    )


# ============================================================
# 2. 课程信息表
# ============================================================

class Course(Base):
    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="课程名称")
    category: Mapped[str] = mapped_column(
        SAEnum("学科辅导", "兴趣特长", "职业技能", "语言学习", "考试考证", "其他"),
        nullable=False, comment="课程分类",
    )
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, comment="课程价格(元)")
    teacher_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="授课老师ID")
    total_hours: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False, comment="总课时(小时)")
    target_audience: Mapped[str] = mapped_column(
        SAEnum("学生", "通用"), nullable=False, default="通用", comment="面向对象"
    )
    is_live: Mapped[int] = mapped_column(Integer, default=0, comment="是否直播课(0=录播,1=直播)")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )


# ============================================================
# 3. 订单/报名信息表
# ============================================================

class OrderInfo(Base):
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程ID")
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, comment="订单金额")
    device_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="设备指纹(设备唯一标识)"
    )
    study_goal: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="学习目标")
    expected_finish_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="预计完成天数")
    order_status: Mapped[str] = mapped_column(
        SAEnum("待支付", "已支付", "学习中", "已完成", "已取消"),
        nullable=False, default="待支付", comment="订单状态",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="报名时间"
    )
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="支付时间")


# ============================================================
# 4. 学习进度表
# ============================================================

class LearningProgress(Base):
    __tablename__ = "learning_progress"

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="进度ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订单ID")
    total_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="累计学习时长(分钟)")
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近活跃时间")
    completion_rate: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0.00, comment="完成率(0-100)"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )


# ============================================================
# 5. 退费申请表
# ============================================================

class RefundRequest(Base):
    __tablename__ = "refund_request"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退费ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="退费原因")
    study_minutes_before_refund: Mapped[int] = mapped_column(
        Integer, default=0, comment="退费前已学习时长(分钟)"
    )
    refund_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, comment="退费金额")
    refund_status: Mapped[str] = mapped_column(
        SAEnum("待审核", "已同意", "已拒绝"), nullable=False, default="待审核", comment="退费状态"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="申请时间"
    )


# ============================================================
# 6. 黑名单扩展表
# ============================================================

class BlacklistExtra(Base):
    __tablename__ = "blacklist_extra"

    entry_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="记录ID")
    type: Mapped[str] = mapped_column(
        SAEnum("学号", "身份证号", "手机号", "设备指纹"), nullable=False, comment="黑名单类型"
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="加入原因")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="过期时间(NULL=永久)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )


# ============================================================
# 7. 打赏记录表
# ============================================================

class DonationRecord(Base):
    __tablename__ = "donation_record"

    donation_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="打赏ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="打赏用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联直播课程ID")
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, comment="打赏金额(元)")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="打赏时间"
    )
