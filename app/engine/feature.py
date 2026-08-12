"""Engine 层：将报名业务记录转换为可解释的风险特征。"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CredentialVerification, DeviceBinding, Enrollment, RefundRequest


def build_enrollment_features(session: Session, enrollment: Enrollment) -> dict[str, float]:
    """构建本次报名本身的金额与时间特征。"""
    enroll_at = enrollment.enroll_at or datetime.now()
    return {
        "enrollment_paid_amount": float(enrollment.paid_amount),
        "enrollment_discount_amount": float(enrollment.discount_amount),
        "enrollment_is_night": float(enroll_at.hour < 6),
    }


def build_user_features(session: Session, user_id: str) -> dict[str, float]:
    """构建用户报名频次与累计金额特征。"""
    seven_days_ago = datetime.now() - timedelta(days=7)
    enrollment_count = session.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user_id)
    ) or 0
    enrollment_count_7d = session.scalar(
        select(func.count()).select_from(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.enroll_at >= seven_days_ago,
        )
    ) or 0
    total_paid = session.scalar(
        select(func.coalesce(func.sum(Enrollment.paid_amount), 0)).where(Enrollment.user_id == user_id)
    ) or 0
    return {
        "user_enrollments_total": float(enrollment_count),
        "user_enrollments_7d": float(enrollment_count_7d),
        "user_total_enrollment_amount": float(total_paid),
    }


def build_device_features(session: Session, user_id: str) -> dict[str, float]:
    """构建设备关联账号数特征；只使用已哈希的设备指纹。"""
    binding = session.scalar(
        select(DeviceBinding)
        .where(DeviceBinding.user_id == user_id)
        .order_by(DeviceBinding.last_seen_at.desc())
        .limit(1)
    )
    if binding is None:
        return {"device_linked_users_7d": 0.0, "device_is_new": 1.0}

    seven_days_ago = datetime.now() - timedelta(days=7)
    linked_users = session.scalar(
        select(func.count(func.distinct(DeviceBinding.user_id))).where(
            DeviceBinding.device_fingerprint_hash == binding.device_fingerprint_hash,
            DeviceBinding.last_seen_at >= seven_days_ago,
        )
    ) or 0
    return {
        "device_linked_users_7d": float(linked_users),
        "device_is_new": float(binding.first_seen_at >= seven_days_ago),
    }


def build_features(session: Session, enrollment: Enrollment) -> dict[str, float]:
    """合并用户、设备、报名三类特征，作为规则引擎的唯一输入。"""
    return {
        **build_user_features(session, enrollment.user_id),
        **build_device_features(session, enrollment.user_id),
        **build_enrollment_features(session, enrollment),
    }


def build_refund_features(session: Session, refund: RefundRequest) -> dict[str, float]:
    """构建退款申请的学习使用与历史退款特征。"""
    ninety_days_ago = datetime.now() - timedelta(days=90)
    enrollment = session.get(Enrollment, refund.enrollment_id)
    if enrollment is None:
        raise ValueError(f"退款关联的报名记录不存在: {refund.enrollment_id}")
    refund_count = session.scalar(
        select(func.count())
        .select_from(RefundRequest)
        .join(Enrollment, RefundRequest.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.user_id == enrollment.user_id, RefundRequest.apply_at >= ninety_days_ago)
    ) or 0
    refund_amount = session.scalar(
        select(func.coalesce(func.sum(RefundRequest.refund_amount), 0))
        .select_from(RefundRequest)
        .join(Enrollment, RefundRequest.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.user_id == enrollment.user_id, RefundRequest.apply_at >= ninety_days_ago)
    ) or 0
    return {
        "refund_amount": float(refund.refund_amount),
        "refund_study_minutes_before_refund": float(refund.study_minutes_before_refund),
        "refund_user_count_90d": float(refund_count),
        "refund_user_amount_90d": float(refund_amount),
    }


def build_credential_features(
    session: Session, verification: CredentialVerification
) -> dict[str, float]:
    """构建学历/身份认证的失败次数与当前结果特征。"""
    thirty_days_ago = datetime.now() - timedelta(days=30)
    failure_count = session.scalar(
        select(func.count()).select_from(CredentialVerification).where(
            CredentialVerification.user_id == verification.user_id,
            CredentialVerification.status == "审核失败",
            CredentialVerification.submit_at >= thirty_days_ago,
        )
    ) or 0
    return {
        "credential_is_failed": float(verification.status == "审核失败"),
        "credential_failure_count_30d": float(failure_count),
    }
