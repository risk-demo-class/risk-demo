"""
特征工程模块: 通过 ORM 查询教育业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户维度特征
  order_xxx  = 订单维度特征
  addr_xxx   = 地址/设备维度特征
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Course, DeviceFingerprint, LearningProgress, OrderInfo, RefundRequest,
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
# 用户维度特征 (14 个)
# ============================================================

async def _feat_user_total_enrollments(db: AsyncSession, user_id: str) -> float:
    """历史报名总数"""
    return await _count(OrderInfo, db, user_id=user_id)


async def _feat_user_enrollments_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天报名数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_enrollments_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天报名数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(OrderInfo).where(
        OrderInfo.user_id == user_id,
        OrderInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    """历史总消费金额"""
    return await _sum(OrderInfo, "total_amount", db, user_id=user_id)


async def _feat_user_avg_course_amount(
    db: AsyncSession, user_id: str, total_enrollments: float | None = None,
) -> float:
    """平均课程金额 = 总金额 / 报名数"""
    if total_enrollments is None:
        total_enrollments = await _feat_user_total_enrollments(db, user_id)
    if total_enrollments == 0:
        return 0
    total_amount = await _feat_user_total_amount(db, user_id)
    return round(total_amount / total_enrollments, 2)


async def _feat_user_max_course_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔课程金额"""
    stmt = select(func.coalesce(func.max(OrderInfo.total_amount), 0)).where(
        OrderInfo.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    """退费总次数"""
    return await _count(RefundRequest, db, user_id=user_id)


async def _feat_user_refund_rate(
    db: AsyncSession, user_id: str, total_enrollments: float | None = None,
) -> float:
    """退费率 = 退费次数 / 总报名数"""
    if total_enrollments is None:
        total_enrollments = await _feat_user_total_enrollments(db, user_id)
    if total_enrollments == 0:
        return 0
    refund_count = await _feat_user_refund_count(db, user_id)
    return round(refund_count / total_enrollments, 4)


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    """退费总金额"""
    return await _sum(RefundRequest, "refund_amount", db, user_id=user_id)


async def _feat_user_total_study_minutes(db: AsyncSession, user_id: str) -> float:
    """总学习时长 (分钟)"""
    return await _sum(LearningProgress, "total_minutes", db, user_id=user_id)


async def _feat_user_avg_completion_rate(
    db: AsyncSession, user_id: str,
) -> float:
    """平均完课率"""
    return await _avg(LearningProgress, "completion_rate", db, user_id=user_id)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """取消报名次数 (status='已取消')"""
    return await _count(OrderInfo, db, user_id=user_id, status='已取消')


async def _feat_user_device_count(db: AsyncSession, user_id: str) -> float:
    """使用设备数"""
    stmt = select(func.count(func.distinct(DeviceFingerprint.fingerprint))).where(
        DeviceFingerprint.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_course_category_count(db: AsyncSession, user_id: str) -> float:
    """报名课程类别数 (DISTINCT)"""
    stmt = select(func.count(func.distinct(Course.category))).select_from(
        OrderInfo
    ).join(Course, OrderInfo.course_id == Course.course_id).where(
        OrderInfo.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 订单维度特征 (8 个)
# ============================================================

async def _feat_order_total_amount(db: AsyncSession, order_id: str) -> float:
    """订单金额"""
    stmt = select(OrderInfo.total_amount).where(OrderInfo.order_id == order_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    return float(row) if row else 0.0


async def _feat_order_course_count(db: AsyncSession, order_id: str) -> float:
    """订单课程数 (教育场景一般为1, 但支持多课程报名)"""
    # 教育版每订单只关联 1 门课, 返回 1 或 0
    stmt = select(func.count()).select_from(OrderInfo).where(OrderInfo.order_id == order_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_order_is_first_course(db: AsyncSession, order_id: str) -> float:
    """是否首课 (该用户的第一笔报名)"""
    row = (await db.execute(
        select(OrderInfo.user_id, OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if not row:
        return 0.0
    user_id, create_time = row.user_id, row.create_time
    earlier = (await db.execute(
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.create_time < create_time,
        )
    )).scalar() or 0
    return 1.0 if earlier == 0 else 0.0


async def _feat_order_discount_amount(db: AsyncSession, order_id: str) -> float:
    """优惠金额: 课程原价 - 实付金额"""
    row = (await db.execute(
        select(OrderInfo.total_amount, Course.price)
        .join(Course, OrderInfo.course_id == Course.course_id)
        .where(OrderInfo.order_id == order_id)
    )).first()
    if not row:
        return 0.0
    paid = float(row.total_amount)
    original = float(row.price)
    return round(max(original - paid, 0), 2)


async def _feat_order_discount_rate(db: AsyncSession, order_id: str) -> float:
    """优惠率 = 优惠金额 / 课程原价"""
    row = (await db.execute(
        select(OrderInfo.total_amount, Course.price)
        .join(Course, OrderInfo.course_id == Course.course_id)
        .where(OrderInfo.order_id == order_id)
    )).first()
    if not row:
        return 0.0
    paid = float(row.total_amount)
    original = float(row.price)
    if original == 0:
        return 0.0
    return round(max(original - paid, 0) / original, 4)


async def _feat_order_enroll_hour(db: AsyncSession, order_id: str) -> float:
    """报名时间 (小时 0-23), 用于判断深夜/凌晨报名"""
    row = (await db.execute(
        select(OrderInfo.create_time).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.create_time:
        return float(row.create_time.hour)
    return 0.0


async def _feat_order_study_goal_length(db: AsyncSession, order_id: str) -> float:
    """学习目标字数 (信息量), 监控'填假目标'行为"""
    row = (await db.execute(
        select(OrderInfo.study_goal).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.study_goal:
        return float(len(row.study_goal))
    return 0.0


async def _feat_order_expected_days(db: AsyncSession, order_id: str) -> float:
    """预期完成天数"""
    row = (await db.execute(
        select(OrderInfo.expected_finish_days).where(OrderInfo.order_id == order_id)
    )).first()
    if row and row.expected_finish_days:
        return float(row.expected_finish_days)
    return 0.0


# ============================================================
# 地址/设备维度特征 (3 个)
# ============================================================

async def _feat_addr_device_count(db: AsyncSession, user_id: str) -> float:
    """用户设备指纹总数"""
    stmt = select(func.count(func.distinct(DeviceFingerprint.fingerprint))).where(
        DeviceFingerprint.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_ip_count(db: AsyncSession, user_id: str) -> float:
    """不同 IP 数量"""
    stmt = select(func.count(func.distinct(DeviceFingerprint.ip))).where(
        DeviceFingerprint.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_is_new_device(
    db: AsyncSession, user_id: str,
) -> float:
    """是否新设备 (该用户设备数 <= 1)"""
    cnt = await _feat_addr_device_count(db, user_id)
    return 1.0 if cnt <= 1 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征 (复用 total_enrollments 减少 SQL)"""
    total_enrollments = await _feat_user_total_enrollments(db, user_id)

    independent_features = {
        "user_enrollments_30d": _feat_user_enrollments_30d,
        "user_enrollments_7d": _feat_user_enrollments_7d,
        "user_total_amount": _feat_user_total_amount,
        "user_max_course_amount": _feat_user_max_course_amount,
        "user_refund_count": _feat_user_refund_count,
        "user_refund_amount": _feat_user_refund_amount,
        "user_total_study_minutes": _feat_user_total_study_minutes,
        "user_avg_completion_rate": _feat_user_avg_completion_rate,
        "user_cancel_count": _feat_user_cancel_count,
        "user_device_count": _feat_user_device_count,
        "user_course_category_count": _feat_user_course_category_count,
    }
    features = {name: await func(db, user_id) for name, func in independent_features.items()}
    features["user_total_enrollments"] = total_enrollments

    # 派生特征: 传 total_enrollments 避免再查
    features["user_avg_course_amount"] = await _feat_user_avg_course_amount(
        db, user_id, total_enrollments=total_enrollments,
    )
    features["user_refund_rate"] = await _feat_user_refund_rate(
        db, user_id, total_enrollments=total_enrollments,
    )

    return features


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个订单维度特征."""
    feat_funcs = {
        "order_total_amount": _feat_order_total_amount,
        "order_course_count": _feat_order_course_count,
        "order_is_first_course": _feat_order_is_first_course,
        "order_discount_amount": _feat_order_discount_amount,
        "order_discount_rate": _feat_order_discount_rate,
        "order_enroll_hour": _feat_order_enroll_hour,
        "order_study_goal_length": _feat_order_study_goal_length,
        "order_expected_days": _feat_order_expected_days,
    }
    return {name: await func(db, order_id) for name, func in feat_funcs.items()}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个地址/设备维度特征."""
    return {
        "addr_device_count": await _feat_addr_device_count(db, user_id),
        "addr_ip_count": await _feat_addr_ip_count(db, user_id),
        "addr_is_new_device": await _feat_addr_is_new_device(db, user_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 25 维特征名 + 字典派发表 (教育行业)")
    print("=" * 60)

    user_feats = [
        ("user_total_enrollments",     "历史报名总数"),
        ("user_enrollments_7d",        "近 7 天报名数"),
        ("user_enrollments_30d",       "近 30 天报名数"),
        ("user_total_amount",          "历史总消费金额"),
        ("user_avg_course_amount",     "平均课程金额"),
        ("user_max_course_amount",     "最大单笔课程金额"),
        ("user_refund_count",          "退费总次数"),
        ("user_refund_rate",           "退费率"),
        ("user_refund_amount",         "退费总金额"),
        ("user_total_study_minutes",   "总学习时长(分钟)"),
        ("user_avg_completion_rate",   "平均完课率"),
        ("user_cancel_count",          "取消报名次数"),
        ("user_device_count",          "使用设备数"),
        ("user_course_category_count", "报名课程类别数"),
    ]
    order_feats = [
        ("order_total_amount",      "订单金额"),
        ("order_course_count",      "订单课程数"),
        ("order_is_first_course",   "是否首课 (0/1)"),
        ("order_discount_amount",   "优惠金额"),
        ("order_discount_rate",     "优惠率"),
        ("order_enroll_hour",       "报名时间(小时)"),
        ("order_study_goal_length", "学习目标字数"),
        ("order_expected_days",     "预期完成天数"),
    ]
    addr_feats = [
        ("addr_device_count",    "设备指纹数"),
        ("addr_ip_count",        "不同IP数"),
        ("addr_is_new_device",   "是否新设备 (0/1)"),
    ]
    all_groups = [("用户 (14)", user_feats), ("订单 (8)", order_feats), ("地址/设备 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
