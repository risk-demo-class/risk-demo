"""教育行业 25 维特征工程。

为兼容老师的决策引擎和 XGBoost，保留原 25 个特征键及三个公共函数签名；
其业务含义已替换为课程报名、退费、学习、直播打赏和设备关联风险。
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, LearningProgress, LiveReward, OrderInfo, RefundRequest, UserInfo


async def _scalar(db: AsyncSession, statement) -> float:
    return float((await db.execute(statement)).scalar() or 0)


async def _feat_user_total_orders(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db, select(func.count()).select_from(OrderInfo).where(OrderInfo.user_id == user_id)
    )


async def _feat_user_orders_since(
    db: AsyncSession, user_id: str, days: int
) -> float:
    since = datetime.now() - timedelta(days=days)
    return await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id, OrderInfo.order_time >= since
        ),
    )


async def _feat_user_total_amount(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.coalesce(func.sum(OrderInfo.total_amount - OrderInfo.discount_amount), 0))
        .select_from(OrderInfo)
        .where(OrderInfo.user_id == user_id),
    )


async def _feat_user_avg_order_amount(
    db: AsyncSession, user_id: str, total_orders: float | None = None
) -> float:
    total_orders = total_orders if total_orders is not None else await _feat_user_total_orders(db, user_id)
    if total_orders <= 0:
        return 0.0
    return round(await _feat_user_total_amount(db, user_id) / total_orders, 2)


async def _feat_user_max_order_amount(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.coalesce(func.max(OrderInfo.total_amount - OrderInfo.discount_amount), 0))
        .select_from(OrderInfo)
        .where(OrderInfo.user_id == user_id),
    )


def _refund_query(user_id: str):
    return select(RefundRequest).join(
        OrderInfo, RefundRequest.order_id == OrderInfo.order_id
    ).where(OrderInfo.user_id == user_id)


async def _feat_user_refund_count(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.count()).select_from(RefundRequest).join(
            OrderInfo, RefundRequest.order_id == OrderInfo.order_id
        ).where(OrderInfo.user_id == user_id),
    )


async def _feat_user_low_study_refund_count(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.count()).select_from(RefundRequest).join(
            OrderInfo, RefundRequest.order_id == OrderInfo.order_id
        ).where(
            OrderInfo.user_id == user_id,
            RefundRequest.study_minutes_before_refund < 30,
        ),
    )


async def _feat_user_refund_amount(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.coalesce(func.sum(RefundRequest.refund_amount), 0))
        .select_from(RefundRequest)
        .join(OrderInfo, RefundRequest.order_id == OrderInfo.order_id)
        .where(OrderInfo.user_id == user_id),
    )


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id, OrderInfo.status == "已取消"
        ),
    )


async def _feat_user_large_reward_count(db: AsyncSession, user_id: str) -> float:
    return await _scalar(
        db,
        select(func.count()).select_from(LiveReward).where(
            LiveReward.user_id == user_id, LiveReward.reward_amount >= 500
        ),
    )


async def _feat_user_device_count(db: AsyncSession, user_id: str) -> float:
    devices: set[str] = set()
    registered = (await db.execute(
        select(UserInfo.device_id).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    if registered:
        devices.add(registered)
    devices.update(filter(None, (await db.execute(
        select(LearningProgress.device_id).where(LearningProgress.user_id == user_id)
    )).scalars().all()))
    devices.update(filter(None, (await db.execute(
        select(LiveReward.device_id).where(LiveReward.user_id == user_id)
    )).scalars().all()))
    return float(len(devices))


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个学员/账号历史特征。"""
    total_orders = await _feat_user_total_orders(db, user_id)
    refund_count = await _feat_user_refund_count(db, user_id)
    low_study_refunds = await _feat_user_low_study_refund_count(db, user_id)
    return {
        "user_total_orders": total_orders,
        "user_orders_30d": await _feat_user_orders_since(db, user_id, 30),
        "user_orders_7d": await _feat_user_orders_since(db, user_id, 7),
        "user_total_amount": await _feat_user_total_amount(db, user_id),
        "user_avg_order_amount": await _feat_user_avg_order_amount(db, user_id, total_orders),
        "user_max_order_amount": await _feat_user_max_order_amount(db, user_id),
        "user_refund_count": refund_count,
        "user_postsale_count": low_study_refunds,
        "user_refund_rate": round(refund_count / total_orders, 4) if total_orders else 0.0,
        "user_postsale_rate": round(low_study_refunds / refund_count, 4) if refund_count else 0.0,
        "user_refund_amount": await _feat_user_refund_amount(db, user_id),
        "user_cancel_count": await _feat_user_cancel_count(db, user_id),
        "user_complaint_count": await _feat_user_large_reward_count(db, user_id),
        "user_address_count": await _feat_user_device_count(db, user_id),
    }


def _night_flag(value: datetime | None) -> float:
    return 1.0 if value and (value.hour >= 23 or value.hour < 6) else 0.0


async def _course_order_features(db: AsyncSession, entity_id: str) -> dict[str, float] | None:
    row = (await db.execute(
        select(OrderInfo, Course.total_hours)
        .join(Course, OrderInfo.course_id == Course.course_id)
        .where(OrderInfo.order_id == entity_id)
    )).first()
    if not row:
        return None
    order, total_hours = row
    original = float(order.total_amount)
    discount = float(order.discount_amount)
    interval = -1.0
    if order.payment_time:
        interval = max((order.payment_time - order.order_time).total_seconds(), 0.0)
    return {
        "order_total_amount": original - discount,
        "order_item_count": 1.0,
        "order_sku_count": float(total_hours),
        "order_discount_amount": discount,
        "order_discount_rate": round(discount / original, 4) if original else 0.0,
        "order_pay_interval_sec": interval,
        "order_is_night": _night_flag(order.order_time),
        "order_category_count": 1.0,
    }


async def _refund_features(db: AsyncSession, entity_id: str) -> dict[str, float] | None:
    row = (await db.execute(
        select(RefundRequest, OrderInfo.total_amount, OrderInfo.order_time)
        .join(OrderInfo, RefundRequest.order_id == OrderInfo.order_id)
        .where(RefundRequest.refund_id == entity_id)
    )).first()
    if not row:
        return None
    refund, order_amount, order_time = row
    amount = float(refund.refund_amount)
    original = float(order_amount)
    return {
        "order_total_amount": amount,
        "order_item_count": 1.0,
        "order_sku_count": float(refund.study_minutes_before_refund),
        "order_discount_amount": 0.0,
        "order_discount_rate": round(amount / original, 4) if original else 0.0,
        "order_pay_interval_sec": max((refund.apply_time - order_time).total_seconds(), 0.0),
        "order_is_night": _night_flag(refund.apply_time),
        "order_category_count": 1.0,
    }


async def _reward_features(db: AsyncSession, entity_id: str) -> dict[str, float] | None:
    reward = (await db.execute(
        select(LiveReward).where(LiveReward.reward_id == entity_id)
    )).scalar_one_or_none()
    if not reward:
        return None
    return {
        "order_total_amount": float(reward.reward_amount),
        "order_item_count": 1.0,
        "order_sku_count": 1.0,
        "order_discount_amount": 0.0,
        "order_discount_rate": 0.0,
        "order_pay_interval_sec": 0.0,
        "order_is_night": _night_flag(reward.reward_time),
        "order_category_count": 1.0,
    }


async def _learning_features(db: AsyncSession, entity_id: str) -> dict[str, float] | None:
    row = (await db.execute(
        select(LearningProgress, OrderInfo.total_amount, OrderInfo.discount_amount)
        .join(OrderInfo, LearningProgress.order_id == OrderInfo.order_id)
        .where(LearningProgress.progress_id == entity_id)
    )).first()
    if not row:
        return None
    progress, amount, discount = row
    original = float(amount)
    discount_value = float(discount)
    return {
        "order_total_amount": original - discount_value,
        "order_item_count": 1.0,
        "order_sku_count": float(progress.total_minutes),
        "order_discount_amount": discount_value,
        "order_discount_rate": round(discount_value / original, 4) if original else 0.0,
        "order_pay_interval_sec": float(progress.completion_rate),
        "order_is_night": _night_flag(progress.last_active_at),
        "order_category_count": 1.0,
    }


async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """计算 8 个业务单据特征；ID 可对应报名、退费、打赏或学习进度。"""
    for loader in (_course_order_features, _refund_features, _reward_features, _learning_features):
        features = await loader(db, order_id)
        if features is not None:
            return features
    return {name: 0.0 for name in (
        "order_total_amount", "order_item_count", "order_sku_count",
        "order_discount_amount", "order_discount_rate", "order_pay_interval_sec",
        "order_is_night", "order_category_count",
    )}


async def _device_users(db: AsyncSession, device_id: str) -> set[str]:
    users = set((await db.execute(
        select(UserInfo.user_id).where(UserInfo.device_id == device_id)
    )).scalars().all())
    users.update((await db.execute(
        select(LearningProgress.user_id).where(LearningProgress.device_id == device_id)
    )).scalars().all())
    users.update((await db.execute(
        select(LiveReward.user_id).where(LiveReward.device_id == device_id)
    )).scalars().all())
    return users


async def compute_address_features(
    db: AsyncSession, user_id: str, receive_id: str | None = None
) -> dict[str, float]:
    """兼容旧函数名；教育版计算设备/身份关联特征。"""
    device_id = receive_id or (await db.execute(
        select(UserInfo.device_id).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    if not device_id:
        return {"addr_total_count": 0.0, "addr_province_count": 0.0, "addr_is_new": 1.0}
    users = await _device_users(db, device_id)
    identity_count = await _scalar(
        db,
        select(func.count(func.distinct(UserInfo.id_card_hash))).select_from(UserInfo).where(
            UserInfo.device_id == device_id, UserInfo.id_card_hash.is_not(None)
        ),
    )
    event_count = await _scalar(
        db,
        select(func.count()).select_from(LearningProgress).where(
            LearningProgress.device_id == device_id
        ),
    ) + await _scalar(
        db,
        select(func.count()).select_from(LiveReward).where(LiveReward.device_id == device_id),
    )
    return {
        "addr_total_count": float(len(users)),
        "addr_province_count": identity_count,
        "addr_is_new": 1.0 if event_count <= 1 else 0.0,
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    else:
        features.update(await compute_order_features(db, ""))
    features.update(await compute_address_features(db, user_id, receive_id))
    return {name: float(value or 0) for name, value in features.items()}
