"""
EduRisk ORM 模型 — 24 张表
17 张教育业务表 + 7 张风控表
业务表: 学员/课程/校区/报名/缴费/退费/考试/作业/考勤/优惠券/投诉/设备/账号...
风控表: risk_event / risk_feature / risk_assessment / risk_case / risk_rule / risk_user_profile / risk_blacklist
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, Date, DECIMAL, Enum, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_id(prefix: str) -> str:
    """生成带业务前缀的主键,如 ENR_xxx / PAY_xxx。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ============================================================
# 一、教育业务表 (17 张)
# ============================================================

class UserInfo(Base):
    """学员信息表"""
    __tablename__ = "user_info"
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    register_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    user_level: Mapped[str] = mapped_column(String(16), default="普通")  # 普通/黄金/铂金/钻石
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profile: Mapped["RiskUserProfile"] = relationship(back_populates="user", uselist=False)


class CourseInfo(Base):
    """课程表"""
    __tablename__ = "course_info"
    course_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_name: Mapped[str] = mapped_column(String(128))
    category_id: Mapped[str] = mapped_column(String(32), index=True)      # 课程分类
    school_id: Mapped[str] = mapped_column(String(32), index=True)        # 所属校区
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    status: Mapped[str] = mapped_column(String(16), default="在售")       # 在售/下架
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CourseCategory(Base):
    """课程分类表"""
    __tablename__ = "course_category"
    category_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    category_name: Mapped[str] = mapped_column(String(64))


class School(Base):
    """校区表"""
    __tablename__ = "school"
    school_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    school_name: Mapped[str] = mapped_column(String(64))
    province: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(32))


class ClassInfo(Base):
    """班级表"""
    __tablename__ = "class_info"
    class_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(32), index=True)
    school_id: Mapped[str] = mapped_column(String(32), index=True)
    teacher_id: Mapped[str] = mapped_column(String(32), index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=0)


class Enrollment(Base):
    """报名单表 (对应电商的订单表)"""
    __tablename__ = "enrollment"
    enrollment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    school_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="已报名")     # 已报名/已缴费/已退费/已取消
    total_amount: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    coupon_amount: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    pay_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EnrollmentDetail(Base):
    """报名明细表 (一门报名单可含多个班级/课程)"""
    __tablename__ = "enrollment_detail"
    detail_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(String(32), index=True)
    course_id: Mapped[str] = mapped_column(String(32), index=True)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)


class PaymentRecord(Base):
    """缴费记录表 (对应电商的支付表)"""
    __tablename__ = "payment_record"
    payment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    pay_method: Mapped[str] = mapped_column(String(16), default="微信")   # 微信/支付宝/银行卡
    pay_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(16), default="成功")       # 成功/失败/退款中
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RefundRecord(Base):
    """退费记录表 (对应电商的售后表)"""
    __tablename__ = "refund_record"
    refund_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    apply_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(16), default="申请中")     # 申请中/已退费/已拒绝
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExamRecord(Base):
    """考试记录表 (教育特色风险场景: 替考/作弊/异常作答)"""
    __tablename__ = "exam_record"
    exam_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    course_id: Mapped[str] = mapped_column(String(32), index=True)
    exam_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)     # 答题时长(秒)
    score: Mapped[float] = mapped_column(DECIMAL(5, 1), default=0)
    cheat_flag: Mapped[bool] = mapped_column(Boolean, default=False)      # 是否被系统标记作弊
    cheat_reason: Mapped[str] = mapped_column(String(255), default="")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HomeworkRecord(Base):
    """作业记录表"""
    __tablename__ = "homework_record"
    homework_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    course_id: Mapped[str] = mapped_column(String(32), index=True)
    submit_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    submit_count: Mapped[int] = mapped_column(Integer, default=1)         # 今日提交次数
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AttendanceRecord(Base):
    """考勤记录表"""
    __tablename__ = "attendance_record"
    attendance_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    check_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    is_absent: Mapped[bool] = mapped_column(Boolean, default=False)       # 是否缺勤
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CouponRecord(Base):
    """优惠券记录表 (对应电商的优惠券, 教育场景: 奖学金券/体验券)"""
    __tablename__ = "coupon_record"
    coupon_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    coupon_name: Mapped[str] = mapped_column(String(64), default="体验课优惠券")
    amount: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    status: Mapped[str] = mapped_column(String(16), default="未使用")     # 未使用/已使用/已过期
    get_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    use_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ComplaintRecord(Base):
    """投诉记录表 (对应电商的物流投诉)"""
    __tablename__ = "complaint_record"
    complaint_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    enrollment_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(16), default="待处理")     # 待处理/已解决/已驳回
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceRecord(Base):
    """设备记录表 (同一设备多账号 = 批量注册信号)"""
    __tablename__ = "device_record"
    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    device_fp: Mapped[str] = mapped_column(String(128), index=True)       # 设备指纹
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TeacherInfo(Base):
    """教师表"""
    __tablename__ = "teacher_info"
    teacher_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    teacher_name: Mapped[str] = mapped_column(String(64))
    school_id: Mapped[str] = mapped_column(String(32), index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AccountInfo(Base):
    """账号表 (对应电商用户账号, 一个学员可多账号)"""
    __tablename__ = "account_info"
    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    account_name: Mapped[str] = mapped_column(String(64))
    reg_device_fp: Mapped[str] = mapped_column(String(128), default="")
    reg_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(16), default="正常")       # 正常/冻结/风控
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ============================================================
# 二、风控表 (7 张)
# ============================================================

class RiskEvent(Base):
    """风险事件表 — 每次风控检查一条记录"""
    __tablename__ = "risk_event"
    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(16), index=True)       # 报名/缴费/退费/考试/作业
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)        # 业务单据号
    event_data: Mapped[dict] = mapped_column(JSON, default=dict)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    features: Mapped[list["RiskFeature"]] = relationship(back_populates="event")
    assessment: Mapped["RiskAssessment | None"] = relationship(back_populates="event", uselist=False)


class RiskFeature(Base):
    """特征快照表 — 每次检查存 25 条"""
    __tablename__ = "risk_feature"
    feature_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), ForeignKey("risk_event.event_id"), index=True)
    feature_name: Mapped[str] = mapped_column(String(64))
    feature_value: Mapped[float] = mapped_column(DECIMAL(16, 4), default=0)

    event: Mapped[RiskEvent] = relationship(back_populates="features")


class RiskAssessment(Base):
    """风险评估表 — 与事件 1:1"""
    __tablename__ = "risk_assessment"
    assessment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(32), ForeignKey("risk_event.event_id"), index=True)
    rule_score: Mapped[float] = mapped_column(DECIMAL(6, 2), default=0)
    ml_score: Mapped[float] = mapped_column(DECIMAL(6, 2), default=0)
    final_score: Mapped[float] = mapped_column(DECIMAL(6, 2), default=0)
    risk_level: Mapped[str] = mapped_column(String(8), default="低")      # 低/中/高/极高
    decision: Mapped[str] = mapped_column(String(8), default="通过")      # 通过/标记/人工审核/拒绝
    hit_rules: Mapped[dict] = mapped_column(JSON, default=list)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    event: Mapped[RiskEvent] = relationship(back_populates="assessment")
    case: Mapped["RiskCase | None"] = relationship(back_populates="assessment", uselist=False)


class RiskCase(Base):
    """风险案件表 — 人工审核/拒绝时生成"""
    __tablename__ = "risk_case"
    case_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(32), ForeignKey("risk_assessment.assessment_id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(16), default="")
    case_status: Mapped[str] = mapped_column(String(8), default="待审核")  # 待审核/审核中/已通过/已拒绝/已关闭
    assignee: Mapped[str] = mapped_column(String(32), default="")          # 审核人
    reviewer: Mapped[str] = mapped_column(String(32), default="")
    review_comment: Mapped[str] = mapped_column(String(500), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    close_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assessment: Mapped[RiskAssessment] = relationship(back_populates="case")


class RiskRule(Base):
    """风控规则表 — 30 条预置,JSON 条件表达式"""
    __tablename__ = "risk_rule"
    rule_id: Mapped[str] = mapped_column(String(8), primary_key=True)     # R001-R030
    rule_name: Mapped[str] = mapped_column(String(64))
    rule_category: Mapped[str] = mapped_column(String(16), index=True)    # 报名/缴费/退费/考试/账号/内容
    event_type: Mapped[str] = mapped_column(String(16), default="通用")
    rule_condition: Mapped[dict] = mapped_column(JSON)                    # {"field":..., "op":..., "value":...}
    risk_level: Mapped[str] = mapped_column(String(8), default="中")      # 低/中/高/极高
    risk_score: Mapped[int] = mapped_column(Integer, default=40)
    action: Mapped[str] = mapped_column(String(16), default="标记")       # 通过/标记/人工审核/拒绝
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)            # 越大越先匹配
    description: Mapped[str] = mapped_column(String(255), default="")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("idx_rule_enabled", "is_enabled", "priority"),)


class RiskUserProfile(Base):
    """用户风险画像表 — 每用户 1 条"""
    __tablename__ = "risk_user_profile"
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("user_info.user_id"), primary_key=True)
    total_checks: Mapped[int] = mapped_column(Integer, default=0)         # 累计检查次数
    total_cases: Mapped[int] = mapped_column(Integer, default=0)          # 累计案件数
    max_score: Mapped[float] = mapped_column(DECIMAL(6, 2), default=0)    # 历史最高分
    avg_score: Mapped[float] = mapped_column(DECIMAL(6, 2), default=0)
    risk_tag: Mapped[str] = mapped_column(String(16), default="正常")     # 正常/关注/高危
    first_check_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_check_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[UserInfo] = relationship(back_populates="profile")


class RiskBlacklist(Base):
    """黑名单表"""
    __tablename__ = "risk_blacklist"
    blacklist_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(16), default="人工")       # 人工/AI/规则
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(8), default="生效")        # 生效/解除
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
