"""
特征工程模块: 通过 ORM 查询业务数据, 计算 20 个教育风控特征.

【特征命名规范】前缀用于 decision.py 决定 risk_feature 表的 entity_type
  user_xxx      = 用户维度特征
  course_xxx    = 课程维度特征
  order_xxx     = 订单/支付维度特征
  behavior_xxx  = 学习行为维度特征
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Complaint, Course, DeviceFingerprint, LearningProgress,
    OrderInfo, PaymentAccount, RefundRequest, TeacherInfo, UserInfo,
)


# 通用 SQL 工具
async def _count(model, db: AsyncSession, **filters) -> float:
    """SELECT COUNT(*) FROM model WHERE filters."""
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(SUM(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _avg(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(AVG(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.avg(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (8 个)
# ============================================================

async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """账号年龄(天): register_at 距今天数"""
    row = (await db.execute(
        select(func.datediff(func.now(), UserInfo.register_at))
        .where(UserInfo.user_id == user_id)
    )).scalar()
    return float(row or 0)


async def _feat_user_is_real_name(db: AsyncSession, user_id: str) -> float:
    """是否实名: 1=已认证, 0=未认证"""
    row = (await db.execute(
        select(UserInfo.real_name_status).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_user_role_code(db: AsyncSession, user_id: str) -> float:
    """角色编码: 学生=1, 老师=2, 家长=3"""
    row = (await db.execute(
        select(UserInfo.role).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    if row == "学生":
        return 1.0
    elif row == "老师":
        return 2.0
    elif row == "家长":
        return 3.0
    return 0.0


async def _feat_user_total_enrollments(db: AsyncSession, user_id: str) -> float:
    """历史报名总数"""
    return await _count(OrderInfo, db, user_id=user_id)


async def _feat_user_enrollments_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天报名数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.pay_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_completion_rate(db: AsyncSession, user_id: str) -> float:
    """历史平均课程完成率(%)"""
    return await _avg(LearningProgress, "completion_rate", db, user_id=user_id)


async def _feat_user_refund_rate(db: AsyncSession, user_id: str, total_enrollments: float) -> float:
    """历史退费率 = 退费次数 / 报名总数"""
    if total_enrollments <= 0:
        return 0.0
    refund_count = await _count(RefundRequest, db, user_id=user_id)
    return refund_count / total_enrollments


async def _feat_user_complaint_count(db: AsyncSession, user_id: str) -> float:
    """历史投诉次数"""
    return await _count(Complaint, db, user_id=user_id)


# ============================================================
# 课程维度特征 (4 个)
# ============================================================

async def _feat_course_price(db: AsyncSession, course_id: str) -> float:
    """课程价格"""
    row = (await db.execute(
        select(Course.price).where(Course.course_id == course_id)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_course_category_code(db: AsyncSession, course_id: str) -> float:
    """课程类别哈希编码 (简单映射为数值, 供 ML 用)"""
    row = (await db.execute(
        select(Course.category).where(Course.course_id == course_id)
    )).scalar_one_or_none()
    # 简单数值映射: 考研=1, 公考=2, 职业=3, 语言=4, 素质=5
    mapping = {"考研": 1, "公考": 2, "职业": 3, "语言": 4, "素质": 5}
    return float(mapping.get(row, 0))


async def _feat_course_total_hours(db: AsyncSession, course_id: str) -> float:
    """总课时"""
    row = (await db.execute(
        select(Course.total_hours).where(Course.course_id == course_id)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_course_teacher_rating(db: AsyncSession, course_id: str) -> float:
    """授课教师平均评分"""
    stmt = select(func.coalesce(func.avg(TeacherInfo.avg_rating), 0)).select_from(
        Course
    ).join(
        TeacherInfo, Course.teacher_id == TeacherInfo.teacher_id
    ).where(
        Course.course_id == course_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 订单/支付维度特征 (4 个)
# ============================================================

async def _feat_order_amount(db: AsyncSession, order_id: str) -> float:
    """本次订单金额"""
    if not order_id:
        return 0.0
    row = (await db.execute(
        select(OrderInfo.amount).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_order_pay_hour(db: AsyncSession, order_id: str) -> float:
    """支付时段(0-23)"""
    if not order_id:
        return 0.0
    row = (await db.execute(
        select(func.hour(OrderInfo.pay_time)).where(OrderInfo.order_id == order_id)
    )).scalar_one_or_none()
    return float(row or 0)


async def _feat_user_multi_course_count(db: AsyncSession, user_id: str) -> float:
    """当前同时报名的课程数 (未退款, 非关闭)"""
    stmt = select(func.count(func.distinct(OrderInfo.course_id))).where(
        OrderInfo.user_id == user_id,
        OrderInfo.order_status.in_(["已支付"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_payment_account_count(db: AsyncSession, user_id: str) -> float:
    """绑定的支付账户数"""
    return await _count(PaymentAccount, db, user_id=user_id)


# ============================================================
# 学习行为维度特征 (4 个)
# ============================================================

async def _feat_behavior_today_minutes(db: AsyncSession, user_id: str) -> float:
    """今日累计学习时长(分钟)"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.coalesce(func.sum(LearningProgress.total_minutes), 0)).where(
        LearningProgress.user_id == user_id,
        LearningProgress.last_active_at >= today_start,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_behavior_active_courses(db: AsyncSession, user_id: str) -> float:
    """正在学习中的课程数 (完成率 0%~99%)"""
    stmt = select(func.count()).select_from(LearningProgress).where(
        LearningProgress.user_id == user_id,
        LearningProgress.completion_rate > 0,
        LearningProgress.completion_rate < 100,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_behavior_night_session(db: AsyncSession, user_id: str) -> float:
    """最近活跃是否在凌晨 (22:00-06:00 = 1, 否则 = 0)"""
    row = (await db.execute(
        select(func.hour(LearningProgress.last_active_at))
        .where(LearningProgress.user_id == user_id)
        .order_by(LearningProgress.last_active_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return 0.0
    return 1.0 if row < 6 or row >= 22 else 0.0


async def _feat_behavior_device_count(db: AsyncSession, user_id: str) -> float:
    """关联设备数"""
    stmt = select(func.count(func.distinct(DeviceFingerprint.device_id))).where(
        DeviceFingerprint.user_id == user_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 特征维度列表 (用于 ML 模型, 顺序必须固定)
# ============================================================

FEATURE_COLUMNS = [
    "user_account_age_days",        # 0
    "user_is_real_name",            # 1
    "user_role_code",               # 2
    "user_total_enrollments",       # 3
    "user_enrollments_30d",         # 4
    "user_avg_completion_rate",     # 5
    "user_refund_rate",             # 6
    "user_complaint_count",         # 7
    "course_price",                 # 8
    "course_category_code",         # 9
    "course_total_hours",           # 10
    "course_teacher_rating",        # 11
    "order_amount",                 # 12
    "order_pay_hour",               # 13
    "user_multi_course_count",      # 14
    "user_payment_account_count",   # 15
    "behavior_today_minutes",       # 16
    "behavior_active_courses",      # 17
    "behavior_night_session",       # 18
    "behavior_device_count",        # 19
]

FEATURE_COLUMNS_SET = set(FEATURE_COLUMNS)


# ============================================================
# 聚合函数
# ============================================================

async def compute_user_features(
    db: AsyncSession, user_id: str,
    course_id: str | None = None,
    order_id: str | None = None,
) -> dict[str, float]:
    """计算用户维度 + 课程维度 + 支付维度 + 行为维度特征, 返回 dict."""
    features: dict[str, float] = {}

    # --- 用户维度 (8个) ---
    features["user_account_age_days"] = await _feat_user_account_age_days(db, user_id)
    features["user_is_real_name"] = await _feat_user_is_real_name(db, user_id)
    features["user_role_code"] = await _feat_user_role_code(db, user_id)
    total_enrollments = await _feat_user_total_enrollments(db, user_id)
    features["user_total_enrollments"] = total_enrollments
    features["user_enrollments_30d"] = await _feat_user_enrollments_30d(db, user_id)
    features["user_avg_completion_rate"] = await _feat_user_avg_completion_rate(db, user_id)
    features["user_refund_rate"] = await _feat_user_refund_rate(db, user_id, total_enrollments)
    features["user_complaint_count"] = await _feat_user_complaint_count(db, user_id)

    # --- 课程维度 (4个) ---
    if course_id:
        features["course_price"] = await _feat_course_price(db, course_id)
        features["course_category_code"] = await _feat_course_category_code(db, course_id)
        features["course_total_hours"] = await _feat_course_total_hours(db, course_id)
        features["course_teacher_rating"] = await _feat_course_teacher_rating(db, course_id)
    else:
        features["course_price"] = 0.0
        features["course_category_code"] = 0.0
        features["course_total_hours"] = 0.0
        features["course_teacher_rating"] = 0.0

    # --- 支付维度 (4个) ---
    if order_id:
        features["order_amount"] = await _feat_order_amount(db, order_id)
        features["order_pay_hour"] = await _feat_order_pay_hour(db, order_id)
    else:
        features["order_amount"] = 0.0
        features["order_pay_hour"] = 0.0
    features["user_multi_course_count"] = await _feat_user_multi_course_count(db, user_id)
    features["user_payment_account_count"] = await _feat_user_payment_account_count(db, user_id)

    # --- 行为维度 (4个) ---
    features["behavior_today_minutes"] = await _feat_behavior_today_minutes(db, user_id)
    features["behavior_active_courses"] = await _feat_behavior_active_courses(db, user_id)
    features["behavior_night_session"] = await _feat_behavior_night_session(db, user_id)
    features["behavior_device_count"] = await _feat_behavior_device_count(db, user_id)

    return features


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,  # 保留兼容签名, 教育版不再使用
) -> dict[str, float]:
    """
    统一入口: 计算全部 20 维特征.
    签名兼容电商版 run_risk_check 的调用方式.
    receive_id 参数保留但不使用 (教育无物理地址).
    """
    return await compute_user_features(db, user_id, order_id=order_id)