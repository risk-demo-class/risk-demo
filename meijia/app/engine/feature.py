"""教育行业 25 维特征：账号、报名交易、学习行为三个特征族。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.engine.ml_model import FEATURE_COLUMNS
from app.models_business import (
    BlacklistExtra, Course, EducationCredential, LearningProgress, LiveReward,
    OrderInfo, RefundRequest, UserDevice, UserInfo,
)


ACCOUNT_FEATURES = FEATURE_COLUMNS[:8]
ENROLLMENT_FEATURES = FEATURE_COLUMNS[8:16]
BEHAVIOR_FEATURES = FEATURE_COLUMNS[16:]


def _zero(names: list[str]) -> dict[str, float]:
    return {name: 0.0 for name in names}


def _days(delta) -> float:
    return max(delta.total_seconds() / 86400, 0.0)


def compute_account_features(
    db: Session, user_id: str, *, as_of: datetime | None = None
) -> dict[str, float]:
    """账号/实名/设备/黑名单特征族（8 维）。"""
    now = as_of or datetime.now()
    f = _zero(ACCOUNT_FEATURES)
    user = db.get(UserInfo, user_id)
    if user is None:
        return f

    f["account_age_days"] = _days(now - user.register_at)
    f["is_student"] = float(user.role == "学生")
    f["is_real_name_verified"] = float(user.real_name_status == "已认证")
    f["new_account_flag"] = float(f["account_age_days"] < 7)

    active_since = now - timedelta(days=180)
    fingerprints = list(db.scalars(
        select(UserDevice.device_fingerprint).where(
            UserDevice.user_id == user_id, UserDevice.last_seen_at >= active_since
        )
    ))
    f["device_count_180d"] = float(len(set(fingerprints)))
    if fingerprints:
        count = db.scalar(
            select(func.count(distinct(UserDevice.user_id)))
            .join(UserInfo, UserInfo.user_id == UserDevice.user_id)
            .where(
                UserDevice.device_fingerprint.in_(fingerprints),
                UserDevice.last_seen_at >= active_since,
                UserInfo.role == "学生",
            )
        ) or 0
        f["device_student_count"] = float(count)

    if user.student_id:
        hit = db.scalar(
            select(func.count(BlacklistExtra.entry_id)).where(
                BlacklistExtra.type == "学号",
                BlacklistExtra.value == user.student_id.strip().upper(),
                BlacklistExtra.status == "启用",
                BlacklistExtra.deleted_at.is_(None),
                or_(BlacklistExtra.expire_at.is_(None), BlacklistExtra.expire_at > now),
            )
        ) or 0
        f["student_blacklist_hit"] = float(hit > 0)

    f["user_order_count_30d"] = float(db.scalar(
        select(func.count(OrderInfo.order_id)).where(
            OrderInfo.user_id == user_id,
            OrderInfo.created_at >= now - timedelta(days=30),
        )
    ) or 0)
    return f


def compute_enrollment_features(
    db: Session, order_id: str | None, *, as_of: datetime | None = None
) -> dict[str, float]:
    """课程报名与支付特征族（8 维）。"""
    f = _zero(ENROLLMENT_FEATURES)
    if not order_id:
        return f
    order = db.get(OrderInfo, order_id)
    if order is None:
        return f

    now = as_of or order.paid_at or order.created_at
    paid_states = ("已支付", "部分退款", "已退款")
    start_1h = now - timedelta(hours=1)
    f["buyer_paid_amount_1h"] = float(db.scalar(
        select(func.coalesce(func.sum(OrderInfo.total_amount), 0)).where(
            OrderInfo.user_id == order.user_id,
            OrderInfo.order_status.in_(paid_states),
            OrderInfo.paid_at >= start_1h,
            OrderInfo.paid_at <= now,
        )
    ) or 0)
    f["buyer_order_count_1h"] = float(db.scalar(
        select(func.count(OrderInfo.order_id)).where(
            OrderInfo.user_id == order.user_id,
            OrderInfo.order_status.in_(paid_states),
            OrderInfo.paid_at >= start_1h,
            OrderInfo.paid_at <= now,
        )
    ) or 0)

    learner = aliased(UserInfo)
    recent_orders = list(db.execute(
        select(OrderInfo.learner_user_id, OrderInfo.payment_account_hash)
        .join(learner, learner.user_id == OrderInfo.learner_user_id)
        .where(
            OrderInfo.course_id == order.course_id,
            OrderInfo.order_status.in_(paid_states),
            OrderInfo.created_at >= now - timedelta(days=7),
            OrderInfo.created_at <= now,
            learner.register_at >= OrderInfo.created_at - timedelta(days=7),
        )
    ))
    new_students = {row[0] for row in recent_orders}
    f["course_new_student_count_7d"] = float(len(new_students))

    linked_students: set[str] = set()
    if order.payment_account_hash:
        linked_students.update(row[0] for row in recent_orders if row[1] == order.payment_account_hash)
        f["payment_account_user_count_7d"] = float(len(linked_students))
    subject_devices = set(db.scalars(select(UserDevice.device_fingerprint).where(
        UserDevice.user_id == order.learner_user_id,
        UserDevice.last_seen_at >= now - timedelta(days=180),
    )))
    if subject_devices:
        linked_students.update(db.scalars(
            select(distinct(UserDevice.user_id)).where(
                UserDevice.device_fingerprint.in_(subject_devices),
                UserDevice.last_seen_at >= now - timedelta(days=180),
                UserDevice.user_id.in_(new_students),
            )
        ))
    f["course_linked_new_student_count_7d"] = float(len(linked_students))
    f["order_total_amount"] = float(order.total_amount)
    f["expected_finish_days"] = float(order.expected_finish_days or 0)
    course = db.get(Course, order.course_id)
    price = float(course.price) if course and course.price else 0.0
    f["order_course_price_ratio"] = float(order.total_amount) / price if price else 0.0
    return f


def compute_behavior_features(
    db: Session,
    user_id: str,
    *,
    order_id: str | None = None,
    refund_id: str | None = None,
    live_session_id: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, float]:
    """学习、退费、学历认证、直播打赏特征族（9 维）。"""
    now = as_of or datetime.now()
    f = _zero(BEHAVIOR_FEATURES)
    order = db.get(OrderInfo, order_id) if order_id else None
    refund = db.get(RefundRequest, refund_id) if refund_id else None

    if refund:
        f["study_minutes_before_refund"] = float(refund.study_minutes_before_refund)
        order = db.get(OrderInfo, refund.order_id)
    if order:
        progress = db.scalar(select(LearningProgress).where(
            LearningProgress.user_id == order.learner_user_id,
            LearningProgress.course_id == order.course_id,
        ))
        if progress:
            f["completion_rate"] = float(progress.completion_rate)
            if progress.last_active_at:
                f["days_since_last_active"] = _days(now - progress.last_active_at)

    cutoff = now - timedelta(days=90)
    successful = db.execute(
        select(RefundRequest.refund_amount)
        .join(OrderInfo, OrderInfo.order_id == RefundRequest.order_id)
        .where(
            OrderInfo.user_id == user_id,
            RefundRequest.refund_status == "退款成功",
            RefundRequest.completed_at >= cutoff,
            RefundRequest.completed_at <= now,
        )
    ).all()
    f["user_refund_count_90d"] = float(len(successful))
    f["user_refund_amount_90d"] = float(sum((row[0] or Decimal(0)) for row in successful))
    paid_count = db.scalar(select(func.count(OrderInfo.order_id)).where(
        OrderInfo.user_id == user_id,
        OrderInfo.order_status.in_(("已支付", "部分退款", "已退款")),
        OrderInfo.paid_at >= cutoff,
        OrderInfo.paid_at <= now,
    )) or 0
    f["refund_rate_90d"] = f["user_refund_count_90d"] / paid_count if paid_count else 0.0

    if live_session_id:
        rows = db.execute(select(LiveReward.transaction_type, LiveReward.amount).where(
            LiveReward.user_id == user_id,
            LiveReward.live_session_id == live_session_id,
            LiveReward.reward_status == "成功",
        )).all()
        f["session_reward_net_amount"] = float(sum(
            amount if kind == "打赏" else -amount for kind, amount in rows
        ))

    credential = db.scalar(
        select(EducationCredential).where(EducationCredential.user_id == user_id)
        .order_by(EducationCredential.submitted_at.desc()).limit(1)
    )
    if credential:
        f["credential_mismatch"] = float(credential.verify_status == "不匹配")
        f["credential_no_record"] = float(credential.verify_status == "无记录")
    return f


def compute_all_features(
    db: Session,
    user_id: str,
    *,
    order_id: str | None = None,
    refund_id: str | None = None,
    live_session_id: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, float]:
    features = compute_account_features(db, user_id, as_of=as_of)
    features.update(compute_enrollment_features(db, order_id, as_of=as_of))
    features.update(compute_behavior_features(
        db, user_id, order_id=order_id, refund_id=refund_id,
        live_session_id=live_session_id, as_of=as_of,
    ))
    if list(features) != FEATURE_COLUMNS:
        missing = set(FEATURE_COLUMNS) - set(features)
        extra = set(features) - set(FEATURE_COLUMNS)
        raise RuntimeError(f"特征列不一致: missing={missing}, extra={extra}")
    return features


if __name__ == "__main__":
    print(f"教育特征共 {len(FEATURE_COLUMNS)} 维")
    print(f"账号族={len(ACCOUNT_FEATURES)}, 报名族={len(ENROLLMENT_FEATURES)}, 行为族={len(BEHAVIOR_FEATURES)}")
