"""
在线教育风控特征工程。

固定输出 25 维数值特征，与 ``ml_model.FEATURE_COLUMNS`` 一一对应。
"""
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BusinessEventType
from app.models import (
    BlacklistExtra,
    Course,
    LearningProgress,
    OrderInfo,
    RefundRequest,
    UserInfo,
)


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _scalar(db: AsyncSession, stmt) -> float:
    return _number((await db.execute(stmt)).scalar())


async def _load_context_entities(
    db: AsyncSession,
    *,
    event_type: str,
    source_id: str,
) -> tuple[OrderInfo | None, Course | None, LearningProgress | None, RefundRequest | None]:
    order = None
    progress = None
    refund = None

    if event_type == BusinessEventType.COURSE_PURCHASE.value:
        order = (
            await db.execute(select(OrderInfo).where(OrderInfo.order_id == source_id))
        ).scalar_one_or_none()
    elif event_type == BusinessEventType.REFUND_REQUEST.value:
        refund = (
            await db.execute(select(RefundRequest).where(RefundRequest.refund_id == source_id))
        ).scalar_one_or_none()
        if refund:
            order = (
                await db.execute(select(OrderInfo).where(OrderInfo.order_id == refund.order_id))
            ).scalar_one_or_none()
    elif event_type == BusinessEventType.LEARNING_ACTIVITY.value:
        progress = (
            await db.execute(select(LearningProgress).where(LearningProgress.progress_id == source_id))
        ).scalar_one_or_none()
        if progress:
            order = (
                await db.execute(select(OrderInfo).where(OrderInfo.order_id == progress.order_id))
            ).scalar_one_or_none()

    course = None
    if order:
        course = (
            await db.execute(select(Course).where(Course.course_id == order.course_id))
        ).scalar_one_or_none()
        if progress is None:
            progress = (
                await db.execute(
                    select(LearningProgress).where(LearningProgress.order_id == order.order_id).limit(1)
                )
            ).scalar_one_or_none()
    return order, course, progress, refund


async def _active_extra_blacklist(
    db: AsyncSession,
    type_name: str,
    value: str | None,
) -> float:
    if not value:
        return 0.0
    now = datetime.now()
    count = await _scalar(
        db,
        select(func.count()).select_from(BlacklistExtra).where(
            BlacklistExtra.type == type_name,
            BlacklistExtra.value == value,
            BlacklistExtra.status == "ACTIVE",
            or_(BlacklistExtra.expire_at.is_(None), BlacklistExtra.expire_at > now),
        ),
    )
    return 1.0 if count else 0.0


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 11 个用户行为特征。"""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)
    days_7 = now - timedelta(days=7)
    days_30 = now - timedelta(days=30)
    days_90 = now - timedelta(days=90)

    user = (
        await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))
    ).scalar_one()
    account_age = max((now - user.register_at).days, 0)

    paid = OrderInfo.payment_status == "PAID"
    purchase_count_1h = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id, paid, OrderInfo.created_at >= hour_ago,
        ),
    )
    purchase_amount_1h = await _scalar(
        db,
        select(func.coalesce(func.sum(OrderInfo.total_amount), 0)).where(
            OrderInfo.user_id == user_id, paid, OrderInfo.created_at >= hour_ago,
        ),
    )
    purchase_count_7d = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id, paid, OrderInfo.created_at >= days_7,
        ),
    )
    purchase_amount_7d = await _scalar(
        db,
        select(func.coalesce(func.sum(OrderInfo.total_amount), 0)).where(
            OrderInfo.user_id == user_id, paid, OrderInfo.created_at >= days_7,
        ),
    )
    refund_count_90d = await _scalar(
        db,
        select(func.count()).select_from(RefundRequest).where(
            RefundRequest.user_id == user_id, RefundRequest.created_at >= days_90,
        ),
    )
    refund_amount_90d = await _scalar(
        db,
        select(func.coalesce(func.sum(RefundRequest.refund_amount), 0)).where(
            RefundRequest.user_id == user_id, RefundRequest.created_at >= days_90,
        ),
    )
    purchase_count_90d = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id, OrderInfo.created_at >= days_90,
        ),
    )
    learning_minutes_30d = await _scalar(
        db,
        select(func.coalesce(func.sum(LearningProgress.total_minutes), 0)).where(
            LearningProgress.user_id == user_id,
            func.coalesce(LearningProgress.last_active_at, LearningProgress.created_at) >= days_30,
        ),
    )
    avg_completion = await _scalar(
        db,
        select(func.coalesce(func.avg(LearningProgress.completion_rate), 0)).where(
            LearningProgress.user_id == user_id,
        ),
    )

    return {
        "user_account_age_days": float(account_age),
        "user_role_teacher_flag": 1.0 if user.role == "teacher" else 0.0,
        "user_purchase_count_1h": purchase_count_1h,
        "user_purchase_amount_1h": purchase_amount_1h,
        "user_purchase_count_7d": purchase_count_7d,
        "user_purchase_amount_7d": purchase_amount_7d,
        "user_refund_count_90d": refund_count_90d,
        "user_refund_amount_90d": refund_amount_90d,
        "user_refund_rate_90d": round(refund_count_90d / purchase_count_90d, 4) if purchase_count_90d else 0.0,
        "user_learning_minutes_30d": learning_minutes_30d,
        "user_avg_completion_rate": round(avg_completion, 4),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    event_type: str,
    source_id: str,
) -> dict[str, float]:
    """一次性计算并返回固定 25 维教育特征。"""
    features = await compute_user_features(db, user_id)
    user = (
        await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))
    ).scalar_one()
    order, course, progress, refund = await _load_context_entities(
        db, event_type=event_type, source_id=source_id,
    )

    now = datetime.now()
    days_7 = now - timedelta(days=7)
    days_30 = now - timedelta(days=30)
    course_new_users = 0.0
    course_users = 0.0
    if course:
        course_new_users = await _scalar(
            db,
            select(func.count(distinct(OrderInfo.user_id))).select_from(OrderInfo).join(
                UserInfo, OrderInfo.user_id == UserInfo.user_id,
            ).where(
                OrderInfo.course_id == course.course_id,
                OrderInfo.created_at >= days_7,
                UserInfo.register_at >= days_7,
            ),
        )
        course_users = await _scalar(
            db,
            select(func.count(distinct(OrderInfo.user_id))).select_from(OrderInfo).where(
                OrderInfo.course_id == course.course_id,
                OrderInfo.created_at >= days_7,
            ),
        )

    student_only_count = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).join(
            Course, OrderInfo.course_id == Course.course_id,
        ).where(
            OrderInfo.user_id == user_id,
            OrderInfo.created_at >= days_30,
            Course.audience_role == "student",
        ),
    )

    device_users = 0.0
    if user.device_id:
        device_users = await _scalar(
            db,
            select(func.count(distinct(UserInfo.user_id))).select_from(UserInfo).where(
                UserInfo.device_id == user.device_id,
                UserInfo.register_at >= days_30,
            ),
        )

    features.update({
        "order_total_amount": _number(order.total_amount if order else 0),
        "course_price": _number(course.price if course else 0),
        "course_is_student_only": 1.0 if course and course.audience_role == "student" else 0.0,
        "course_new_account_purchase_count_7d": course_new_users,
        "course_distinct_users_7d": course_users,
        "student_only_purchase_count_30d": student_only_count,
        "current_study_minutes": _number(progress.total_minutes if progress else 0),
        "current_completion_rate": _number(progress.completion_rate if progress else 0),
        "refund_study_minutes": _number(refund.study_minutes_before_refund if refund else 0),
        "refund_amount": _number(refund.refund_amount if refund else 0),
        "device_distinct_users_30d": device_users,
        "student_id_blacklisted": await _active_extra_blacklist(db, "student_id", user.student_id),
        "id_card_blacklisted": await _active_extra_blacklist(db, "id_card", user.id_card_hash),
        "device_id_blacklisted": await _active_extra_blacklist(db, "device_id", user.device_id),
    })
    return features


if __name__ == "__main__":
    from app.engine.ml_model import FEATURE_COLUMNS

    print("教育风控特征数:", len(FEATURE_COLUMNS))
    for index, name in enumerate(FEATURE_COLUMNS, 1):
        print(f"{index:>2}. {name}")
