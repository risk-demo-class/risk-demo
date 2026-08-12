"""教育风控特征工程：仍输出 25 维，供原规则引擎和 XGBoost 使用。"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Enrollment, LearningProgress, LiveReward, RefundRequest, UserInfo


async def _scalar(db: AsyncSession, statement) -> float:
    return float((await db.execute(statement)).scalar() or 0)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    now = datetime.now()
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one()
    total = await _scalar(db, select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user_id))
    amount = await _scalar(db, select(func.coalesce(func.sum(Enrollment.total_amount), 0)).where(Enrollment.user_id == user_id))
    refund_count = await _scalar(db, select(func.count()).select_from(RefundRequest).where(RefundRequest.user_id == user_id))
    refund_amount = await _scalar(db, select(func.coalesce(func.sum(RefundRequest.refund_amount), 0)).where(RefundRequest.user_id == user_id))
    progress = await _scalar(db, select(func.coalesce(func.sum(LearningProgress.total_minutes), 0)).where(LearningProgress.user_id == user_id))
    device_users = await _scalar(db, select(func.count()).select_from(UserInfo).where(UserInfo.device_id == user.device_id))
    orders_7d = await _scalar(db, select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user_id, Enrollment.payment_time >= now - timedelta(days=7)))
    orders_30d = await _scalar(db, select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user_id, Enrollment.payment_time >= now - timedelta(days=30)))
    rewards_30d = await _scalar(db, select(func.coalesce(func.sum(LiveReward.amount), 0)).where(LiveReward.user_id == user_id, LiveReward.reward_time >= now - timedelta(days=30)))
    max_amount = await _scalar(db, select(func.coalesce(func.max(Enrollment.total_amount), 0)).where(Enrollment.user_id == user_id))
    return {
        "user_total_orders": total, "user_orders_30d": orders_30d, "user_orders_7d": orders_7d,
        "user_total_amount": amount, "user_avg_order_amount": round(amount / total, 2) if total else 0,
        "user_max_order_amount": max_amount, "user_refund_count": refund_count,
        "user_postsale_count": refund_count, "user_refund_rate": round(refund_count / total, 4) if total else 0,
        "user_postsale_rate": round(refund_count / total, 4) if total else 0,
        "user_refund_amount": refund_amount, "user_cancel_count": 0.0,
        "user_complaint_count": device_users, "user_address_count": progress,
        "user_account_age_days": max((now - user.register_at).days, 0), "user_device_user_count": device_users,
        "user_live_reward_30d": rewards_30d,
    }


async def compute_order_features(db: AsyncSession, enrollment_id: str | None) -> dict[str, float]:
    if not enrollment_id:
        return {}
    row = (await db.execute(select(Enrollment).where(Enrollment.enrollment_id == enrollment_id))).scalar_one_or_none()
    if not row:
        return {}
    course_count = await _scalar(db, select(func.count()).select_from(Enrollment).where(Enrollment.user_id == row.user_id))
    return {
        "order_total_amount": float(row.total_amount), "order_item_count": 1.0,
        "order_sku_count": 1.0, "order_discount_amount": 0.0, "order_discount_rate": 0.0,
        "order_pay_interval_sec": 0.0, "order_is_night": 1.0 if 0 <= row.payment_time.hour < 6 else 0.0,
        "order_category_count": course_count,
    }


async def compute_address_features(db: AsyncSession, user_id: str, receive_id: str | None = None) -> dict[str, float]:
    """保留 addr_* 命名以兼容固定的 25 维 XGBoost 输入；教育语义为设备/实名维度。"""
    user = (await db.execute(select(UserInfo).where(UserInfo.user_id == user_id))).scalar_one()
    device_users = await _scalar(db, select(func.count()).select_from(UserInfo).where(UserInfo.device_id == user.device_id))
    return {"addr_total_count": device_users, "addr_province_count": float(user.real_name_status), "addr_is_new": 1.0 if (datetime.now() - user.register_at).days < 7 else 0.0}


async def compute_all_features(db: AsyncSession, user_id: str, order_id: str | None = None, receive_id: str | None = None) -> dict[str, float]:
    features = await compute_user_features(db, user_id)
    features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    # 训练模型仍固定读取 25 个既有列；新增教育特征可供规则使用。
    return features
