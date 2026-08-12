"""
教育风控特征工程模块: 通过 ORM 查询教育业务数据, 计算 11 个风控特征.

特征命名规范 (前缀决定 risk_feature 表的 entity_type):
  user_xxx    = 用户维度特征
  order_xxx   = 订单维度特征
  course_xxx  = 课程维度特征
  learn_xxx   = 学习维度特征
  device_xxx  = 设备维度特征
  donation_xxx = 打赏维度特征
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Course,
    DonationRecord,
    OrderInfo,
    RefundRequest,
    UserInfo,
)

logger = logging.getLogger(__name__)


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


# ============================================================
# 用户维度特征 (6 个)
# ============================================================

async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    """历史报名总数"""
    return await _count(OrderInfo, db, user_id=user_id)


async def _feat_user_order_amount_1h(db: AsyncSession, user_id: str) -> float:
    """近 1 小时累计订单金额"""
    since = datetime.now() - timedelta(hours=1)
    stmt = select(func.coalesce(func.sum(OrderInfo.total_amount), 0)).select_from(
        OrderInfo
    ).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count_90d(db: AsyncSession, user_id: str) -> float:
    """近 90 天退款次数"""
    since = datetime.now() - timedelta(days=90)
    return await _count(RefundRequest, db, user_id=user_id, refund_status="待审核") + \
           await _count(RefundRequest, db, user_id=user_id, refund_status="已同意")
    # 注意: 同时用两个条件时, 需要分开查 (status 不是 kwarg filter)


async def _feat_user_refund_amount_90d(db: AsyncSession, user_id: str) -> float:
    """近 90 天累计退款金额"""
    since = datetime.now() - timedelta(days=90)
    stmt = select(func.coalesce(func.sum(RefundRequest.refund_amount), 0)).select_from(
        RefundRequest
    ).where(
        RefundRequest.user_id == user_id,
        RefundRequest.create_time >= since,
        RefundRequest.refund_status.in_(["待审核", "已同意"]),
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_days_since_register(db: AsyncSession, user_id: str) -> float:
    """注册至今的天数"""
    row = (await db.execute(
        select(UserInfo.register_at).where(UserInfo.user_id == user_id)
    )).first()
    if row and row.register_at:
        delta = datetime.now() - row.register_at
        return float(max(delta.days, 0))
    return 0.0


async def _feat_user_is_teacher(db: AsyncSession, user_id: str) -> float:
    """用户是否为老师 (1=是, 0=否)"""
    row = (await db.execute(
        select(UserInfo.role).where(UserInfo.user_id == user_id)
    )).first()
    return 1.0 if row and row.role == "老师" else 0.0


# ============================================================
# 订单维度特征 (3 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """当前订单总金额"""
    row = (await db.execute(
        select(OrderInfo.total_amount).where(OrderInfo.order_id == order_id)
    )).first()
    return float(row.total_amount) if row and row.total_amount else 0.0


async def _feat_course_is_student_only(db: AsyncSession, course_id: str) -> float:
    """课程是否学生专属 (1=学生专用, 0=通用)"""
    row = (await db.execute(
        select(Course.target_audience).where(Course.course_id == course_id)
    )).first()
    return 1.0 if row and row.target_audience == "学生" else 0.0


async def _feat_device_linked_students(db: AsyncSession, device_fingerprint: str | None) -> float:
    """同一设备指纹关联的不同学员数"""
    if not device_fingerprint:
        return 0.0
    stmt = select(
        func.count(func.distinct(OrderInfo.user_id))
    ).select_from(OrderInfo).where(
        OrderInfo.device_fingerprint == device_fingerprint,
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 学习维度特征 (1 个)
# ============================================================

async def _feat_study_minutes_before_refund(
    db: AsyncSession, user_id: str, course_id: str,
) -> float:
    """用户在该课程的总学习时长 (分钟). 用于 R002 0学时退费判断."""
    stmt = select(
        func.coalesce(func.sum(func.coalesce(
            getattr(__import__('app.models', fromlist=['LearningProgress']).LearningProgress,
                   'total_minutes'), 0)), 0)
    )
    # 简化: 直接从 learning_progress 查
    from app.models import LearningProgress
    stmt2 = select(
        func.coalesce(func.sum(LearningProgress.total_minutes), 0)
    ).select_from(LearningProgress).where(
        LearningProgress.user_id == user_id,
        LearningProgress.course_id == course_id,
    )
    return float((await db.execute(stmt2)).scalar() or 0)


# ============================================================
# 打赏维度特征 (1 个)
# ============================================================

async def _feat_donation_amount(db: AsyncSession, donation_id: str) -> float:
    """单次打赏金额"""
    row = (await db.execute(
        select(DonationRecord.amount).where(DonationRecord.donation_id == donation_id)
    )).first()
    return float(row.amount) if row and row.amount else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 6 个用户维度特征. 复用 total_orders 给派生特征."""
    total_orders = await _feat_user_total_orders(db, user_id)

    features = {
        "user_total_orders": total_orders,
        "user_order_amount_1h": await _feat_user_order_amount_1h(db, user_id),
        "user_refund_count_90d": await _feat_user_refund_count_90d(db, user_id),
        "user_refund_amount_90d": await _feat_user_refund_amount_90d(db, user_id),
        "user_days_since_register": await _feat_user_days_since_register(db, user_id),
        "user_is_teacher": await _feat_user_is_teacher(db, user_id),
    }
    return features


async def compute_order_features(
    db: AsyncSession, order_id: str, course_id: str,
    device_fingerprint: str | None = None,
) -> dict[str, float]:
    """计算 3 个订单维度特征."""
    return {
        "order_total_amount": await _feat_order_total_amount(db, order_id),
        "course_is_student_only": await _feat_course_is_student_only(db, course_id),
        "device_linked_students": await _feat_device_linked_students(db, device_fingerprint),
    }


async def compute_course_features(db: AsyncSession, course_id: str) -> dict[str, float]:
    """计算 1 个课程维度特征: 7 天内新账号报名数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(
        func.count(func.distinct(OrderInfo.user_id))
    ).select_from(OrderInfo).where(
        OrderInfo.course_id == course_id,
        OrderInfo.create_time >= since,
    )
    val = float((await db.execute(stmt)).scalar() or 0)
    return {"course_new_students_7d": val}


async def compute_learning_features(
    db: AsyncSession, user_id: str, course_id: str,
) -> dict[str, float]:
    """计算 1 个学习维度特征: 用户在某课程的总学习时长."""
    return {
        "study_minutes_before_refund": await _feat_study_minutes_before_refund(
            db, user_id, course_id,
        ),
    }


async def compute_donation_features(
    db: AsyncSession, donation_id: str, user_id: str,
) -> dict[str, float]:
    """计算打赏相关特征: 打赏金额 + 用户注册天数."""
    return {
        "donation_amount": await _feat_donation_amount(db, donation_id),
        "user_days_since_register": await _feat_user_days_since_register(db, user_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    course_id: str | None = None,
    device_fingerprint: str | None = None,
    donation_id: str | None = None,
    event_type: str = "报名",
) -> dict[str, float]:
    """一次性计算全部特征并合并返回. 根据 event_type 决定算哪些维度."""
    features = await compute_user_features(db, user_id)

    if event_type == "报名" and order_id:
        course_id_for_order = course_id
        if not course_id_for_order:
            # 从订单反查课程
            row = (await db.execute(
                select(OrderInfo.course_id).where(OrderInfo.order_id == order_id)
            )).first()
            if row:
                course_id_for_order = row.course_id
        if course_id_for_order:
            features.update(await compute_order_features(
                db, order_id, course_id_for_order, device_fingerprint,
            ))
            features.update(await compute_course_features(db, course_id_for_order))
            features.update(await compute_learning_features(
                db, user_id, course_id_for_order,
            ))

    elif event_type == "退费申请" and order_id:
        # 从订单反查课程
        row = (await db.execute(
            select(OrderInfo.course_id).where(OrderInfo.order_id == order_id)
        )).first()
        if row:
            features.update(await compute_learning_features(db, user_id, row.course_id))

    elif event_type == "打赏" and donation_id:
        features.update(await compute_donation_features(db, donation_id, user_id))

    return features


# ============================================================
# Demo: 展示 11 维特征名 + 分类 + 字典派发表 — 无需 DB
# 跑法: python app/engine/feature_edu.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("教育特征工程 — 11 维特征名 + 字典派发表")
    print("=" * 60)

    user_feats = [
        ("user_total_orders",        "历史报名总数"),
        ("user_order_amount_1h",     "近1小时累计订单金额"),
        ("user_refund_count_90d",    "近90天退款次数"),
        ("user_refund_amount_90d",   "近90天累计退款金额"),
        ("user_days_since_register", "注册至今的天数"),
        ("user_is_teacher",          "是否老师(1=是,0=否)"),
    ]
    order_feats = [
        ("order_total_amount",       "订单总金额"),
        ("course_is_student_only",   "课程是否学生专属(1=是)"),
        ("device_linked_students",   "同设备关联学员数"),
    ]
    course_feats = [
        ("course_new_students_7d",   "近7天该课程新报名人数"),
    ]
    learn_feats = [
        ("study_minutes_before_refund", "退费前已学习时长(分钟)"),
    ]
    donation_feats = [
        ("donation_amount",          "打赏金额"),
    ]
    all_groups = [
        ("用户 (6)", user_feats),
        ("订单 (3)", order_feats),
        ("课程 (1)", course_feats),
        ("学习 (1)", learn_feats),
        ("打赏 (1)", donation_feats),
    ]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<28} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (教育风控专用)")
    print("\n" + "=" * 60)
    print("特征按 event_type 维度分配:")
    print("  报名     → 用户(6) + 订单(3) + 课程(1) + 学习(1) = 11 维")
    print("  退费申请 → 用户(6) + 学习(1) = 7 维")
    print("  打赏     → 用户(6) + 打赏(1) = 7 维")
