"""
教育风控系统 - 业务表 ORM (10 张)
只读映射教育业务系统的核心实体 (用户/学籍/教师/课程/订单/学习进度/退费/投诉/支付账户/设备指纹)
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
# 用户基础
# ============================================================

class UserInfo(Base):
    """用户信息表 — 教育版: 加 role/real_name_status/account_age_days"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名")
    role: Mapped[str] = mapped_column(
        Enum("学生", "老师", "家长", name="user_role_enum"),
        nullable=False, comment="角色",
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    real_name_status: Mapped[int] = mapped_column(Integer, default=0, comment="实名认证 0=未认证 1=已认证")
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, comment="账号年龄(天)")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class StudentProfile(Base):
    """学籍档案 — 关联学生身份信息"""
    __tablename__ = "student_profile"

    profile_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="学籍档案ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联用户ID")
    student_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="学号")
    school_name: Mapped[str] = mapped_column(String(200), comment="学校名称")
    grade: Mapped[str] = mapped_column(String(50), comment="年级/班级")
    id_card_hash: Mapped[str] = mapped_column(String(128), comment="身份证号(SHA-256)")
    parent_phone: Mapped[str] = mapped_column(String(20), comment="家长手机号")


class TeacherInfo(Base):
    """教师信息 — 师资认证与评级"""
    __tablename__ = "teacher_info"

    teacher_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="教师ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="教师姓名")
    cert_no: Mapped[str] = mapped_column(String(100), comment="资质证书编号")
    teach_years: Mapped[int] = mapped_column(Integer, default=0, comment="教龄(年)")
    avg_rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0.00, comment="平均评分")
    course_count: Mapped[int] = mapped_column(Integer, default=0, comment="开课数量")


# ============================================================
# 课程域
# ============================================================

class Course(Base):
    """课程信息表 — 替代电商 SkuInfo"""
    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="课程名称")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程类别(考研/公考/职业/语言/素质)")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="课程价格")
    total_hours: Mapped[int] = mapped_column(Integer, comment="总课时")
    teacher_id: Mapped[str] = mapped_column(String(50), comment="授课教师ID")
    publish_date: Mapped[datetime] = mapped_column(DateTime, comment="上架时间")
    status: Mapped[str] = mapped_column(
        Enum("上架", "下架", name="course_status_enum"),
        default="上架", comment="课程状态",
    )


# ============================================================
# 订单域（教育报名）
# ============================================================

class OrderInfo(Base):
    """订单/报名表 — 加教育专属字段, 去电商字段"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程ID")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单金额")
    pay_time: Mapped[datetime] = mapped_column(DateTime, comment="支付时间")
    study_goal: Mapped[Optional[str]] = mapped_column(String(200), comment="学习目标")
    expected_finish_days: Mapped[Optional[int]] = mapped_column(Integer, comment="预计完成天数")
    order_status: Mapped[str] = mapped_column(
        Enum("待支付", "已支付", "已退款", "已关闭", name="edu_order_status_enum"),
        nullable=False, comment="订单状态",
    )


# ============================================================
# 学习行为域
# ============================================================

class LearningProgress(Base):
    """学习进度 — 刷课检测核心数据源"""
    __tablename__ = "learning_progress"

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="进度ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    course_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="课程ID")
    total_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="累计学习时长(分钟)")
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0.00, comment="完成率(%)")
    last_active_at: Mapped[datetime] = mapped_column(DateTime, comment="最后活跃时间")
    chapter_progress: Mapped[Optional[str]] = mapped_column(Text, comment="章节进度(JSON)")


# ============================================================
# 退费域
# ============================================================

class RefundRequest(Base):
    """退费申请表 — 替代电商 Postsale"""
    __tablename__ = "refund_request"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退费申请ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联订单ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    reason: Mapped[str] = mapped_column(String(500), comment="退费原因")
    study_minutes_before_refund: Mapped[int] = mapped_column(Integer, default=0, comment="退费前已学时长(分钟)")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), comment="退费金额")
    status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过", "已拒绝", name="refund_status_enum"),
        nullable=False, comment="退费状态",
    )
    apply_time: Mapped[datetime] = mapped_column(DateTime, comment="申请时间")


# ============================================================
# 投诉域
# ============================================================

class Complaint(Base):
    """投诉举报 — 全新, 替代物流投诉"""
    __tablename__ = "complaint"

    complaint_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="投诉ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="投诉人")
    course_id: Mapped[str] = mapped_column(String(50), comment="被投诉课程")
    complaint_type: Mapped[str] = mapped_column(
        Enum("虚假宣传", "侵权盗版", "内容违规", "师资不符", name="complaint_type_enum"),
        nullable=False, comment="投诉类型",
    )
    content: Mapped[str] = mapped_column(Text, comment="投诉内容")
    status: Mapped[str] = mapped_column(
        Enum("待处理", "已处理", "已驳回", name="complaint_status_enum"),
        nullable=False, comment="处理状态",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, comment="创建时间")


# ============================================================
# 支付 & 设备域
# ============================================================

class PaymentAccount(Base):
    """支付账户 — 代付洗钱监控"""
    __tablename__ = "payment_account"

    account_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="账户ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    payment_type: Mapped[str] = mapped_column(
        Enum("微信", "支付宝", "银行卡", name="payment_type_enum"),
        nullable=False, comment="支付方式",
    )
    account_hash: Mapped[str] = mapped_column(String(128), comment="账户标识(SHA-256)")
    bind_time: Mapped[datetime] = mapped_column(DateTime, comment="绑定时间")
    is_verified: Mapped[int] = mapped_column(Integer, default=0, comment="是否验证")


class DeviceFingerprint(Base):
    """设备指纹 — 防团伙刷课/批量注册"""
    __tablename__ = "device_fingerprint"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True, comment="设备ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="最近关联用户")
    fingerprint_hash: Mapped[str] = mapped_column(String(256), comment="指纹SHA-256")
    first_seen: Mapped[datetime] = mapped_column(DateTime, comment="首次出现")
    last_seen: Mapped[datetime] = mapped_column(DateTime, comment="最后出现")
    os: Mapped[str] = mapped_column(String(50), comment="操作系统")
    browser: Mapped[str] = mapped_column(String(50), comment="浏览器")
    ip: Mapped[str] = mapped_column(String(50), comment="最近IP")