"""
电商风控系统 - 业务表 ORM (17 张)
只读映射现有业务系统的核心实体 (用户/订单/物流/售后/收货等)
不参与风控决策本身, 但被特征工程和规则引擎查询
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
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与商品基础
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")


class Region(Base):
    """地区表 """
    __tablename__ = "region"

    province: Mapped[str] = mapped_column(String(20), primary_key=True, comment="省")
    city: Mapped[str] = mapped_column(String(20), primary_key=True, comment="市")
    district: Mapped[str] = mapped_column(String(20), primary_key=True, comment="区")


class ProductCategory(Base):
    """商品分类表"""
    __tablename__ = "product_category"

    product_category: Mapped[str] = mapped_column(String(20), primary_key=True, comment="商品类别")


class SkuInfo(Base):
    """商品信息表"""
    __tablename__ = "sku_info"

    sku_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="商品ID")
    sku_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称")
    sku_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="商品价格")
    sku_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="商品类别")
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="商品数量")


# ============================================================
# 订单域
# ============================================================

class OrderStatus(Base):
    """订单状态表"""
    __tablename__ = "order_status"

    order_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="订单状态")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class OrderInfo(Base):
    """订单表"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    receive_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货信息ID")
    order_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="订单状态")


class OrderDetail(Base):
    """订单详细表"""
    __tablename__ = "order_detail"

    order_detail_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单详细ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    sku_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="商品ID")
    sku_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称")
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="商品数量")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="总单价格")
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="折扣金额")
    final_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实付金额")


# ============================================================
# 物流域
# ============================================================

class Logistics(Base):
    """物流表"""
    __tablename__ = "logistics"

    logistics_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物流ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    logistics_tracking: Mapped[Optional[str]] = mapped_column(String(500), comment="物流详细")
    logistics_category: Mapped[Optional[str]] = mapped_column(
        Enum("自提", "物流中转", "专业配送", name="logistics_category_enum"),
        comment="物流类别",
    )


class OrderLogistics(Base):
    """订单物流关联关系表 """
    __tablename__ = "order_logistics"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    logistics_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物流ID")


class LogisticsCompany(Base):
    """物流公司表"""
    __tablename__ = "logistics_company"

    company_name: Mapped[str] = mapped_column(String(20), primary_key=True, comment="物流公司名称")


class LogisticsComplaint(Base):
    """物流投诉问题数据对应表 """
    __tablename__ = "logistics_complaint"

    logistics_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="物流状态")
    logistics_complaint: Mapped[str] = mapped_column(String(100), primary_key=True, comment="物流投诉问题")


class LogisticsComplaintsRecord(Base):
    """物流投诉记录表"""
    __tablename__ = "logistics_complaints_record"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="投诉记录ID")
    logistics_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="物流ID")
    logistics_complaint: Mapped[str] = mapped_column(String(500), nullable=False, comment="物流投诉问题")
    complaint_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投诉时间")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")


# ============================================================
# 售后域
# ============================================================

class PostsaleStatus(Base):
    """售后状态表"""
    __tablename__ = "postsale_status"

    postsale_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="售后状态")
    is_refund: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否退款")
    is_return: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否退货")
    is_exchange: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否换货")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class PostsaleReason(Base):
    """售后原因表"""
    __tablename__ = "postsale_reason"

    postsale_reason: Mapped[str] = mapped_column(String(100), primary_key=True, comment="售后原因")
    product_category: Mapped[Optional[str]] = mapped_column(String(20), comment="商品类别")


class Postsale(Base):
    """售后表"""
    __tablename__ = "postsale"

    postsale_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="售后ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")
    order_detail_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单详细ID")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="退款金额")
    postsale_type: Mapped[Optional[str]] = mapped_column(
        Enum("退款", "退货", "换货", name="postsale_type_enum"),
        comment="售后类型",
    )
    postsale_reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="售后原因")
    postsale_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="售后状态")
    receive_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货信息ID")


class PostsaleLogistics(Base):
    """售后物流关联关系表 """
    __tablename__ = "postsale_logistics"

    postsale_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="售后ID")
    logistics_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物流ID")


# ============================================================
# 收货域
# ============================================================

class ReceiveInfo(Base):
    """收货信息表"""
    __tablename__ = "receive_info"

    receive_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="收货信息ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    receiver_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货人姓名")
    receiver_phone: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货人手机")
    receive_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货省")
    receive_city: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货市")
    receive_district: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货区")
    receive_street_address: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货详细地址")


# ============================================================
# 教育行业业务表
# ============================================================

class EduInstitution(Base):
    """教育机构表: 承载黑白名单、办学许可、资金监管账户等合规特征。"""
    __tablename__ = "edu_institution"
    __table_args__ = (
        Index("idx_edu_inst_license", "license_status", "whitelist_status"),
        Index("idx_edu_inst_account", "supervision_account_no"),
    )

    institution_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="机构ID")
    institution_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="机构名称")
    license_no: Mapped[Optional[str]] = mapped_column(String(80), comment="办学许可证号")
    license_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="许可状态: VALID/EXPIRED/MISSING")
    whitelist_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="监管名单状态: WHITE/GRAY/BLACK")
    supervision_account_no: Mapped[Optional[str]] = mapped_column(String(80), comment="培训收费监管账户")
    province: Mapped[str] = mapped_column(String(30), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(30), nullable=False, comment="市")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")


class EduUserInfo(Base):
    """教育用户表: 学员/家长/教师统一建模, 方便按监护关系和设备聚合。"""
    __tablename__ = "edu_user_info"
    __table_args__ = (
        Index("idx_edu_user_role_age", "role", "age"),
        Index("idx_edu_user_guardian", "guardian_id"),
        Index("idx_edu_user_device", "device_fingerprint"),
        Index("idx_edu_user_register", "register_at"),
    )

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    role: Mapped[str] = mapped_column(String(20), nullable=False, comment="角色: STUDENT/GUARDIAN/TEACHER")
    student_id: Mapped[Optional[str]] = mapped_column(String(50), comment="平台学员号")
    name_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名哈希")
    cert_no_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="证件号哈希")
    age: Mapped[Optional[int]] = mapped_column(Integer, comment="年龄")
    grade: Mapped[Optional[str]] = mapped_column(String(20), comment="年级")
    guardian_id: Mapped[Optional[str]] = mapped_column(String(50), comment="监护人用户ID")
    real_name_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="实名状态: VERIFIED/PENDING/FAILED")
    guardian_consent_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="监护同意状态")
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(100), comment="注册设备指纹")
    ip_region: Mapped[Optional[str]] = mapped_column(String(60), comment="注册IP归属地")
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")


class EduTeacher(Base):
    """教师表: 教师资质、雇佣状态用于课程发布和授课合规校验。"""
    __tablename__ = "edu_teacher"
    __table_args__ = (
        Index("idx_edu_teacher_inst", "institution_id"),
        Index("idx_edu_teacher_qual", "qualification_status"),
    )

    teacher_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="教师ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="用户ID")
    institution_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_institution.institution_id"), nullable=False, comment="机构ID")
    qualification_no_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="教师资格证哈希")
    qualification_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="资质状态: VERIFIED/PENDING/FAILED")
    subject_scope: Mapped[str] = mapped_column(String(80), nullable=False, comment="可授课范围")
    hired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="入职时间")


class EduCourse(Base):
    """课程表: 替代电商 SKU, 保留监管分类、课时、价格和发布状态。"""
    __tablename__ = "edu_course"
    __table_args__ = (
        Index("idx_edu_course_inst", "institution_id", "published_status"),
        Index("idx_edu_course_teacher", "teacher_id"),
        Index("idx_edu_course_type", "subject_type", "training_type"),
        Index("idx_edu_course_price", "price"),
    )

    course_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课程ID")
    institution_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_institution.institution_id"), nullable=False, comment="机构ID")
    teacher_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_teacher.teacher_id"), nullable=False, comment="主讲教师ID")
    course_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="课程名称")
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="学科类型: SUBJECT/NON_SUBJECT")
    training_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="培训类型: ONLINE/OFFLINE/HYBRID")
    delivery_mode: Mapped[str] = mapped_column(String(30), nullable=False, comment="交付方式: LIVE/RECORDED/CLASSROOM")
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False, comment="总课时")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="课程价格")
    published_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="发布状态")
    content_risk_label: Mapped[Optional[str]] = mapped_column(String(30), comment="内容风险标签")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")


class EduEnrollment(Base):
    """报名表: 教育风控主交易单, 绑定学员、课程、机构和预收费口径。"""
    __tablename__ = "edu_enrollment"
    __table_args__ = (
        Index("idx_edu_enroll_user_time", "user_id", "enrolled_at"),
        Index("idx_edu_enroll_course_time", "course_id", "enrolled_at"),
        Index("idx_edu_enroll_device_time", "device_fingerprint", "enrolled_at"),
        Index("idx_edu_enroll_status", "enrollment_status"),
    )

    enrollment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="报名ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="学员用户ID")
    course_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_course.course_id"), nullable=False, comment="课程ID")
    institution_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_institution.institution_id"), nullable=False, comment="机构ID")
    study_goal: Mapped[Optional[str]] = mapped_column(String(100), comment="学习目标")
    expected_finish_days: Mapped[Optional[int]] = mapped_column(Integer, comment="预计完成天数")
    enrollment_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="报名状态")
    prepaid_months: Mapped[int] = mapped_column(Integer, nullable=False, comment="预收费覆盖月份")
    prepaid_hours: Mapped[int] = mapped_column(Integer, nullable=False, comment="预收费课时")
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(100), comment="报名设备指纹")
    ip_region: Mapped[Optional[str]] = mapped_column(String(60), comment="报名IP归属地")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="报名时间")


class EduContract(Base):
    """合同表: 支持示范合同、签署渠道、签署状态特征。"""
    __tablename__ = "edu_contract"
    __table_args__ = (
        Index("idx_edu_contract_enroll", "enrollment_id"),
        Index("idx_edu_contract_signed", "signed_at"),
    )

    contract_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="合同ID")
    enrollment_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_enrollment.enrollment_id"), nullable=False, comment="报名ID")
    contract_version: Mapped[str] = mapped_column(String(30), nullable=False, comment="合同版本")
    standard_template_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否使用示范文本")
    sign_channel: Mapped[str] = mapped_column(String(30), nullable=False, comment="签署渠道")
    contract_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="合同状态")
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签署时间")


class EduPayment(Base):
    """支付表: 重点支撑预收费、监管账户、培训贷和支付工具关联特征。"""
    __tablename__ = "edu_payment"
    __table_args__ = (
        Index("idx_edu_pay_user_time", "user_id", "paid_at"),
        Index("idx_edu_pay_enroll", "enrollment_id"),
        Index("idx_edu_pay_account", "payment_account_hash"),
        Index("idx_edu_pay_compliance", "supervision_account_flag", "loan_flag"),
        Index("idx_edu_pay_amount", "pay_amount"),
    )

    payment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="支付ID")
    enrollment_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_enrollment.enrollment_id"), nullable=False, comment="报名ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="学员用户ID")
    payer_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), comment="付款人用户ID")
    pay_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="支付金额")
    pay_channel: Mapped[str] = mapped_column(String(30), nullable=False, comment="支付渠道")
    payment_account_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="账户类型: SUPERVISION/PRIVATE/THIRD_PARTY")
    payment_account_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="支付账号哈希")
    supervision_account_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否进入监管账户")
    loan_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否培训贷")
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="支付状态")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")


class EduLesson(Base):
    """课节表: 排课时间用于识别节假日/深夜授课和履约异常。"""
    __tablename__ = "edu_lesson"
    __table_args__ = (
        Index("idx_edu_lesson_course_time", "course_id", "scheduled_start_at"),
        Index("idx_edu_lesson_teacher_time", "teacher_id", "scheduled_start_at"),
    )

    lesson_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="课节ID")
    course_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_course.course_id"), nullable=False, comment="课程ID")
    teacher_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_teacher.teacher_id"), nullable=False, comment="教师ID")
    lesson_title: Mapped[str] = mapped_column(String(120), nullable=False, comment="课节标题")
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="计划开始时间")
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="计划结束时间")
    delivery_mode: Mapped[str] = mapped_column(String(30), nullable=False, comment="交付方式")


class EduLearningProgress(Base):
    """学习进度表: 支持刷课、代学、低学时退款等时间窗特征。"""
    __tablename__ = "edu_learning_progress"
    __table_args__ = (
        Index("idx_edu_progress_user_time", "user_id", "last_active_at"),
        Index("idx_edu_progress_enroll", "enrollment_id"),
        Index("idx_edu_progress_device_time", "device_fingerprint", "last_active_at"),
        Index("idx_edu_progress_course", "course_id"),
    )

    progress_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="学习进度ID")
    enrollment_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_enrollment.enrollment_id"), nullable=False, comment="报名ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="学员用户ID")
    course_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_course.course_id"), nullable=False, comment="课程ID")
    lesson_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("edu_lesson.lesson_id"), comment="课节ID")
    watch_minutes: Mapped[int] = mapped_column(Integer, nullable=False, comment="学习分钟数")
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="互动次数")
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, comment="完成率")
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(100), comment="学习设备指纹")
    ip_region: Mapped[Optional[str]] = mapped_column(String(60), comment="学习IP归属地")
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近学习时间")


class EduRefundRequest(Base):
    """退费申请表: 低学时高退款、多次退款、退费难投诉的核心来源。"""
    __tablename__ = "edu_refund_request"
    __table_args__ = (
        Index("idx_edu_refund_user_time", "user_id", "applied_at"),
        Index("idx_edu_refund_enroll", "enrollment_id"),
        Index("idx_edu_refund_status", "refund_status"),
        Index("idx_edu_refund_amount", "refund_amount"),
    )

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="退款ID")
    enrollment_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_enrollment.enrollment_id"), nullable=False, comment="报名ID")
    payment_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("edu_payment.payment_id"), comment="支付ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="学员用户ID")
    refund_reason: Mapped[str] = mapped_column(String(200), nullable=False, comment="退款原因")
    study_minutes_before_refund: Mapped[int] = mapped_column(Integer, nullable=False, comment="退款前学习分钟数")
    consumed_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, comment="已消课时")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="退款金额")
    refund_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="退款状态")
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="申请时间")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审核时间")


class EduComplaint(Base):
    """投诉表: 面向退费难、虚假宣传、违规收费等监管投诉特征。"""
    __tablename__ = "edu_complaint"
    __table_args__ = (
        Index("idx_edu_complaint_user_time", "user_id", "created_at"),
        Index("idx_edu_complaint_inst_time", "institution_id", "created_at"),
        Index("idx_edu_complaint_type", "complaint_type", "complaint_status"),
    )

    complaint_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="投诉ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="投诉用户ID")
    institution_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_institution.institution_id"), nullable=False, comment="机构ID")
    enrollment_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("edu_enrollment.enrollment_id"), comment="报名ID")
    complaint_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="投诉类型")
    complaint_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="投诉状态")
    content_summary: Mapped[Optional[str]] = mapped_column(Text, comment="投诉摘要")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投诉时间")
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="关闭时间")


class EduCertificateVerification(Base):
    """证书/学历核验表: 支持材料复用、核验失败率等反欺诈特征。"""
    __tablename__ = "edu_certificate_verification"
    __table_args__ = (
        Index("idx_edu_cert_user_time", "user_id", "submitted_at"),
        Index("idx_edu_cert_material", "material_hash"),
        Index("idx_edu_cert_result", "verify_result"),
    )

    cert_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="认证ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="用户ID")
    cert_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="证书类型")
    cert_verify_source: Mapped[str] = mapped_column(String(50), nullable=False, comment="核验来源")
    material_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="材料哈希")
    verify_result: Mapped[str] = mapped_column(String(20), nullable=False, comment="核验结果")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="提交时间")
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="核验时间")


class EduLiveReward(Base):
    """直播打赏表: 支持未成年人高额消费和异常打赏聚合。"""
    __tablename__ = "edu_live_reward"
    __table_args__ = (
        Index("idx_edu_reward_user_time", "user_id", "paid_at"),
        Index("idx_edu_reward_session", "live_session_id"),
        Index("idx_edu_reward_amount", "reward_amount"),
    )

    reward_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="打赏ID")
    live_session_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="直播场次ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="打赏用户ID")
    course_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_course.course_id"), nullable=False, comment="课程ID")
    teacher_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_teacher.teacher_id"), nullable=False, comment="教师ID")
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="打赏金额")
    reward_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="打赏状态")
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="支付时间")


class EduDeviceBinding(Base):
    """设备绑定表: 支持同设备多学员、账号共享、代学团伙识别。"""
    __tablename__ = "edu_device_binding"
    __table_args__ = (
        Index("idx_edu_device_fp", "device_fingerprint"),
        Index("idx_edu_device_user", "user_id"),
        Index("idx_edu_device_seen", "last_seen_at"),
    )

    binding_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="绑定ID")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_user_info.user_id"), nullable=False, comment="用户ID")
    device_fingerprint: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备指纹")
    device_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="设备类型")
    ip_region: Mapped[Optional[str]] = mapped_column(String(60), comment="IP归属地")
    bind_channel: Mapped[str] = mapped_column(String(30), nullable=False, comment="绑定渠道")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现时间")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近出现时间")


class EduInstitutionAccountChange(Base):
    """机构收款账户变更表: 支持私账收款、频繁换账户等资金风险识别。"""
    __tablename__ = "edu_institution_account_change"
    __table_args__ = (
        Index("idx_edu_account_inst_time", "institution_id", "changed_at"),
        Index("idx_edu_account_hash", "new_account_hash"),
    )

    change_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="变更ID")
    institution_id: Mapped[str] = mapped_column(String(50), ForeignKey("edu_institution.institution_id"), nullable=False, comment="机构ID")
    old_account_hash: Mapped[Optional[str]] = mapped_column(String(64), comment="原收款账户哈希")
    new_account_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="新收款账户哈希")
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="账户类型")
    change_reason: Mapped[Optional[str]] = mapped_column(String(120), comment="变更原因")
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="变更时间")
