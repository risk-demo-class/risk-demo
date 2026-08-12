"""
教育风控系统 - 业务表 ORM (6 张)
只读映射教育业务系统的核心实体 (用户/课程/订单/学习进度/退费/设备)
不参与风控决策本身, 但被特征工程和规则引擎查询
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与课程基础
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="姓名")
    role: Mapped[str] = mapped_column(
        Enum("学生", "家长", "老师", name="user_role_enum"),
        nullable=False, default="学生", comment="角色",
    )
    student_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="学号")
    real_name_status: Mapped[str] = mapped_column(
        Enum("未认证", "已认证", "认证失败", name="real_name_status_enum"),
        nullable=False, default="未认证", comment="实名认证状态",
    )
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class Course(Base):
    """课程表"""
    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="课程名称")
    category: Mapped[str] = mapped_column(
        Enum("学科辅导", "兴趣培养", "职业技能", "语言学习", "考级考证", "其他", name="course_category_enum"),
        nullable=False, comment="课程类别",
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="课程价格(元)")
    teacher_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="老师ID")
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="总课时(分钟)")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否上架")
    create_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")


# ============================================================
# 报名订单域
# ============================================================

class OrderInfo(Base):
    """报名订单表"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程ID")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实付金额")
    study_goal: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="学习目标")
    expected_finish_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="预期完成天数")
    status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "学习中", "已完成", "已取消", "已退费", name="order_status_enum"),
        nullable=False, default="待支付", comment="订单状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="支付时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="完成时间")


# ============================================================
# 学习进度域
# ============================================================

class LearningProgress(Base):
    """学习进度表"""
    __tablename__ = "learning_progress"

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="进度ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计学习时长(分钟)")
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近学习时间")
    completion_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=0, comment="完课率(0-1)",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="更新时间")


# ============================================================
# 退费域
# ============================================================

class RefundRequest(Base):
    """退费申请表"""
    __tablename__ = "refund_request"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退费ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="退费原因")
    study_minutes_before_refund: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="退费前学习时长(分钟)",
    )
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="退费金额")
    status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过", "已拒绝", name="refund_status_enum"),
        nullable=False, default="待审核", comment="退费状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    resolve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="处理时间")


# ============================================================
# 设备指纹域
# ============================================================

class DeviceFingerprint(Base):
    """设备指纹表"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="设备ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False, comment="设备指纹")
    ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="IP地址")
    create_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现时间")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近出现时间")
