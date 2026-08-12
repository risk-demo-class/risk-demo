"""
特征引擎 — 25 维特征
14 用户维度 + 8 报名维度 + 3 账号维度
特征值从教育业务表(报名/缴费/退费/考试/作业)查询,快照存 risk_feature。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountInfo, ComplaintRecord, DeviceRecord, Enrollment, EnrollmentDetail,
    ExamRecord, PaymentRecord, RefundRecord,
)

logger = logging.getLogger(__name__)

# ============================================================
# 用户维度 14 个 — 签名: fn(db, user_id)
# ============================================================

async def user_total_enrollments(db, user_id):
    """历史报名总数"""
    r = await db.execute(select(func.count(Enrollment.enrollment_id)).where(
        Enrollment.user_id == user_id,
        Enrollment.is_deleted.is_(False)))
    return r.scalar() or 0


async def user_enrollments_30d(db, user_id):
    """近 30 天报名数"""
    th = datetime.now() - timedelta(days=30)
    r = await db.execute(select(func.count(Enrollment.enrollment_id)).where(
        Enrollment.user_id == user_id,
        Enrollment.is_deleted.is_(False),
        Enrollment.create_time >= th))
    return r.scalar() or 0


async def user_enrollments_7d(db, user_id):
    """近 7 天报名数"""
    th = datetime.now() - timedelta(days=7)
    r = await db.execute(select(func.count(Enrollment.enrollment_id)).where(
        Enrollment.user_id == user_id,
        Enrollment.is_deleted.is_(False),
        Enrollment.create_time >= th))
    return r.scalar() or 0


async def user_total_payment(db, user_id):
    """历史缴费总金额"""
    r = await db.execute(select(func.coalesce(func.sum(PaymentRecord.amount), 0)).where(
        PaymentRecord.user_id == user_id,
        PaymentRecord.status == "成功",
        PaymentRecord.is_deleted.is_(False)))
    return float(r.scalar() or 0)


async def user_avg_payment(db, user_id, total_orders=None):
    """平均单笔缴费 — total_orders 外部传入,避免 N+1"""
    total = await user_total_payment(db, user_id)
    if total_orders is None:
        total_orders = await user_total_enrollments(db, user_id)
    return round(total / total_orders, 2) if total_orders else 0.0


async def user_max_payment(db, user_id):
    """最大单笔缴费"""
    r = await db.execute(select(func.coalesce(func.max(PaymentRecord.amount), 0)).where(
        PaymentRecord.user_id == user_id,
        PaymentRecord.status == "成功",
        PaymentRecord.is_deleted.is_(False)))
    return float(r.scalar() or 0)


async def user_refund_count(db, user_id):
    """退费次数"""
    r = await db.execute(select(func.count(RefundRecord.refund_id)).where(
        RefundRecord.user_id == user_id,
        RefundRecord.is_deleted.is_(False)))
    return r.scalar() or 0


async def user_refund_amount(db, user_id):
    """退费总金额"""
    r = await db.execute(select(func.coalesce(func.sum(RefundRecord.amount), 0)).where(
        RefundRecord.user_id == user_id,
        RefundRecord.is_deleted.is_(False)))
    return float(r.scalar() or 0)


async def user_refund_rate(db, user_id, total_orders=None):
    """退费率 = 退费次数 / 报名总数"""
    refund = await user_refund_count(db, user_id)
    if total_orders is None:
        total_orders = await user_total_enrollments(db, user_id)
    return round(refund / total_orders, 4) if total_orders else 0.0


async def user_complaint_count(db, user_id):
    """投诉次数"""
    r = await db.execute(select(func.count(ComplaintRecord.complaint_id)).where(
        ComplaintRecord.user_id == user_id,
        ComplaintRecord.is_deleted.is_(False)))
    return r.scalar() or 0


async def user_cancel_count(db, user_id):
    """取消报名数"""
    r = await db.execute(select(func.count(Enrollment.enrollment_id)).where(
        Enrollment.user_id == user_id,
        Enrollment.status == "已取消",
        Enrollment.is_deleted.is_(False)))
    return r.scalar() or 0


async def user_cheat_count(db, user_id):
    """考试作弊标记次数"""
    r = await db.execute(select(func.count(ExamRecord.exam_id)).where(
        ExamRecord.user_id == user_id,
        ExamRecord.cheat_flag.is_(True),
        ExamRecord.is_deleted.is_(False)))
    return r.scalar() or 0


async def user_exam_count(db, user_id):
    """考试总次数"""
    r = await db.execute(select(func.count(ExamRecord.exam_id)).where(
        ExamRecord.user_id == user_id,
        ExamRecord.is_deleted.is_(False)))
    return r.scalar() or 0


async def user_device_count(db, user_id):
    """设备数量"""
    r = await db.execute(select(func.count(DeviceRecord.device_id)).where(
        DeviceRecord.user_id == user_id,
        DeviceRecord.is_deleted.is_(False)))
    return r.scalar() or 0


# ============================================================
# 报名维度 8 个 — 签名: fn(db, source_id)
# ============================================================

async def enroll_total_amount(db, source_id):
    """报名单金额"""
    r = await db.execute(select(Enrollment.total_amount).where(
        Enrollment.enrollment_id == source_id))
    return float(r.scalar() or 0)


async def enroll_course_count(db, source_id):
    """报名明细课程数"""
    r = await db.execute(select(func.count(EnrollmentDetail.detail_id)).where(
        EnrollmentDetail.enrollment_id == source_id))
    return r.scalar() or 0


async def enroll_category_count(db, source_id):
    """报名课程分类数"""
    from app.models import CourseInfo
    stmt = (
        select(func.count(func.distinct(CourseInfo.category_id)))
        .join(EnrollmentDetail, EnrollmentDetail.course_id == CourseInfo.course_id)
        .where(EnrollmentDetail.enrollment_id == source_id)
    )
    r = await db.execute(stmt)
    return r.scalar() or 0


async def enroll_discount_amount(db, source_id):
    """报名优惠金额(折扣 + 优惠券)"""
    r = await db.execute(select(Enrollment.discount_amount).where(
        Enrollment.enrollment_id == source_id))
    discount = float(r.scalar() or 0)
    r2 = await db.execute(select(Enrollment.coupon_amount).where(
        Enrollment.enrollment_id == source_id))
    coupon = float(r2.scalar() or 0)
    return round(discount + coupon, 2)


async def enroll_discount_rate(db, source_id, total_amount=None):
    """优惠率 = 优惠金额 / 报名金额"""
    discount = await enroll_discount_amount(db, source_id)
    if total_amount is None:
        total_amount = await enroll_total_amount(db, source_id)
    return round(discount / total_amount, 4) if total_amount else 0.0


async def enroll_pay_interval(db, source_id):
    """报名 → 缴费秒数(0 = 未缴费)"""
    r = await db.execute(select(Enrollment.create_time, Enrollment.pay_time).where(
        Enrollment.enrollment_id == source_id))
    row = r.first()
    if not row or not row.pay_time:
        return 0
    return int((row.pay_time - row.create_time).total_seconds())


async def enroll_is_night(db, source_id):
    """是否深夜报名 0/1 (22:00-06:00)"""
    r = await db.execute(select(Enrollment.create_time).where(
        Enrollment.enrollment_id == source_id))
    row = r.first()
    if not row:
        return 0
    return 1 if (row.create_time.hour >= 22 or row.create_time.hour < 6) else 0


async def enroll_coupon_count(db, source_id):
    """报名单是否使用优惠券 0/1"""
    r = await db.execute(select(Enrollment.coupon_amount).where(
        Enrollment.enrollment_id == source_id))
    amount = float(r.scalar() or 0)
    return 1 if amount > 0 else 0


# ============================================================
# 账号维度 3 个 — 签名: fn(db, user_id)
# ============================================================

async def acct_total_count(db, user_id):
    """账号总数"""
    r = await db.execute(select(func.count(AccountInfo.account_id)).where(
        AccountInfo.user_id == user_id,
        AccountInfo.is_deleted.is_(False)))
    return r.scalar() or 0


async def acct_school_count(db, user_id):
    """报名跨校区数"""
    r = await db.execute(select(func.count(func.distinct(Enrollment.school_id))).where(
        Enrollment.user_id == user_id,
        Enrollment.is_deleted.is_(False)))
    return r.scalar() or 0


async def acct_is_new(db, user_id):
    """是否新账号(注册 < 7 天)0/1"""
    r = await db.execute(select(func.min(AccountInfo.reg_time)).where(
        AccountInfo.user_id == user_id,
        AccountInfo.is_deleted.is_(False)))
    row = r.first()
    if not row or not row[0]:
        return 0
    return 1 if (datetime.now() - row[0]).days < 7 else 0


# ============================================================
# 25 维特征注册表
# 加新特征 = 这里加一行 + ml_model.FEATURE_COLUMNS 加字符串 + 重训 + 加测试
# ============================================================

# (特征名, 计算函数, 作用对象)
#   scope="user"    → fn(db, user_id)
#   scope="source"  → fn(db, source_id)  (报名单锚点)
FEATURE_DEFS: list[tuple[str, object, str]] = [
    # ---- 用户维度 14 ----
    ("user_total_enrollments", user_total_enrollments, "user"),
    ("user_enrollments_30d", user_enrollments_30d, "user"),
    ("user_enrollments_7d", user_enrollments_7d, "user"),
    ("user_total_payment", user_total_payment, "user"),
    ("user_avg_payment", user_avg_payment, "user"),
    ("user_max_payment", user_max_payment, "user"),
    ("user_refund_count", user_refund_count, "user"),
    ("user_refund_amount", user_refund_amount, "user"),
    ("user_refund_rate", user_refund_rate, "user"),
    ("user_complaint_count", user_complaint_count, "user"),
    ("user_cancel_count", user_cancel_count, "user"),
    ("user_cheat_count", user_cheat_count, "user"),
    ("user_exam_count", user_exam_count, "user"),
    ("user_device_count", user_device_count, "user"),
    # ---- 报名维度 8 ----
    ("enroll_total_amount", enroll_total_amount, "source"),
    ("enroll_course_count", enroll_course_count, "source"),
    ("enroll_category_count", enroll_category_count, "source"),
    ("enroll_discount_amount", enroll_discount_amount, "source"),
    ("enroll_discount_rate", enroll_discount_rate, "source"),
    ("enroll_pay_interval", enroll_pay_interval, "source"),
    ("enroll_is_night", enroll_is_night, "source"),
    ("enroll_coupon_count", enroll_coupon_count, "source"),
    # ---- 账号维度 3 ----
    ("acct_total_count", acct_total_count, "user"),
    ("acct_school_count", acct_school_count, "user"),
    ("acct_is_new", acct_is_new, "user"),
]


async def compute_all_features(db: AsyncSession, user_id: str, source_id: str) -> dict[str, float]:
    """
    计算 25 维特征,返回 {特征名: 值}。
    user_id: 学员 ID
    source_id: 报名单 ID(报名维度特征的锚点)
    单个特征失败 → 记日志 + 置 0,不阻塞整个流程。
    """
    features: dict[str, float] = {}

    # 公共依赖:报名总数,供 avg/rate 复用,避免 N+1
    total_enrolls = await user_total_enrollments(db, user_id)
    total_amount = await enroll_total_amount(db, source_id)

    for name, fn, scope in FEATURE_DEFS:
        try:
            kwargs = {}
            if name in ("user_avg_payment", "user_refund_rate"):
                kwargs["total_orders"] = total_enrolls
            if name == "enroll_discount_rate":
                kwargs["total_amount"] = total_amount

            anchor = user_id if scope == "user" else source_id
            features[name] = await fn(db, anchor, **kwargs)
        except Exception:
            logger.exception("特征 %s 计算失败,置 0", name)
            features[name] = 0.0

    return features
