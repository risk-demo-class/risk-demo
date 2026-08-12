"""教育行业业务数据 API."""
import json
import math
from datetime import datetime, timedelta
from decimal import Decimal

import ulid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db_async
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import load_enabled_rules, match_rules
from app.models import (
    EduCertificateVerification,
    EduComplaint,
    EduCourse,
    EduDeviceBinding,
    EduEnrollment,
    EduInstitution,
    EduInstitutionAccountChange,
    EduLearningProgress,
    EduLiveReward,
    EduPayment,
    EduRefundRequest,
    EduUserInfo,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo


education_router = APIRouter(prefix="/api/education", tags=["教育业务"])

_STUDENT_SURNAMES = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "刘", "杨"]
_STUDENT_GIVEN_NAMES = [
    "子涵", "雨辰", "思源", "梓萱", "浩然", "欣怡",
    "一诺", "晨曦", "嘉乐", "若曦", "明轩", "语桐",
]


def _student_display_name(user_id: str) -> str:
    """基于学员ID生成稳定展示名, 避免在业务表中落明文真实姓名。"""
    digits = "".join(ch for ch in user_id if ch.isdigit())
    seed = int(digits[-6:] or "0")
    surname = _STUDENT_SURNAMES[seed % len(_STUDENT_SURNAMES)]
    given_name = _STUDENT_GIVEN_NAMES[(seed // len(_STUDENT_SURNAMES)) % len(_STUDENT_GIVEN_NAMES)]
    return f"{surname}{given_name}"


def _risk_id(prefix: str) -> str:
    return f"{prefix}{ulid.new().str.lower()}"


async def _count(db: AsyncSession, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar() or 0)


@education_router.get("/overview")
async def api_education_overview(db: AsyncSession = Depends(get_db_async)):
    """教育业务首页统计: 直接读取 edu_* 业务表."""
    auto_assess_stats = await auto_assess_new_enrollments(db, limit=5000)
    since_7d = datetime.now() - timedelta(days=7)

    total_users = await _count(db, EduUserInfo)
    total_courses = await _count(db, EduCourse)
    total_enrollments = await _count(db, EduEnrollment)
    total_payments = await _count(db, EduPayment)

    risky_prepay = (await db.execute(
        select(func.count()).select_from(EduEnrollment).where(
            (EduEnrollment.prepaid_months > 3) | (EduEnrollment.prepaid_hours > 60)
        )
    )).scalar() or 0
    non_supervised_payments = (await db.execute(
        select(func.count()).select_from(EduPayment).where(
            (EduPayment.supervision_account_flag == False) | (EduPayment.loan_flag == True)
        )
    )).scalar() or 0
    low_study_refunds = (await db.execute(
        select(func.count()).select_from(EduRefundRequest).where(
            EduRefundRequest.study_minutes_before_refund < 5
        )
    )).scalar() or 0
    shared_devices = (await db.execute(
        select(func.count()).select_from(
            select(EduUserInfo.device_fingerprint)
            .where(EduUserInfo.device_fingerprint.is_not(None))
            .group_by(EduUserInfo.device_fingerprint)
            .having(func.count(EduUserInfo.user_id) >= 5)
            .subquery()
        )
    )).scalar() or 0
    active_7d = (await db.execute(
        select(func.count(func.distinct(EduLearningProgress.user_id))).where(
            EduLearningProgress.last_active_at >= since_7d
        )
    )).scalar() or 0
    complaints = await _count(db, EduComplaint)

    return {
        "total_users": total_users,
        "total_courses": total_courses,
        "total_enrollments": total_enrollments,
        "total_payments": total_payments,
        "risky_prepay": int(risky_prepay),
        "non_supervised_payments": int(non_supervised_payments),
        "low_study_refunds": int(low_study_refunds),
        "shared_devices": int(shared_devices),
        "active_7d": int(active_7d),
        "complaints": complaints,
        "auto_assess_created": auto_assess_stats["created_assessments"],
        "auto_assess_cases": auto_assess_stats["created_cases"],
        "auto_assess_skipped": auto_assess_stats["skipped"],
    }


@education_router.get("/enrollments")
async def api_education_enrollments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_flag: str = Query(None, description="风险信号: 预收费超限/非监管账户/培训贷/未成年人同意缺失/机构合规异常/正常"),
    status: str = Query(None, description="报名状态"),
    subject_type: str = Query(None, description="课程类型: SUBJECT/NON_SUBJECT"),
    institution_status: str = Query(None, description="机构合规: normal/abnormal"),
    keyword: str = Query(None, description="报名ID/用户ID/课程/机构关键词"),
    db: AsyncSession = Depends(get_db_async),
):
    """报名列表: 展示教育行业核心业务单据和合规风险字段."""
    offset = (page - 1) * page_size

    filters = []
    if status:
        filters.append(EduEnrollment.enrollment_status == status)
    if subject_type:
        filters.append(EduCourse.subject_type == subject_type)
    if institution_status == "normal":
        filters.append(EduInstitution.license_status == "VALID")
        filters.append(EduInstitution.whitelist_status != "BLACK")
    elif institution_status == "abnormal":
        filters.append((EduInstitution.license_status != "VALID") | (EduInstitution.whitelist_status == "BLACK"))
    if keyword:
        kw = f"%{keyword.strip()}%"
        filters.append(
            (EduEnrollment.enrollment_id.like(kw)) |
            (EduEnrollment.user_id.like(kw)) |
            (EduCourse.course_name.like(kw)) |
            (EduInstitution.institution_name.like(kw))
        )
    if risk_flag == "预收费超限":
        filters.append((EduEnrollment.prepaid_months > 3) | (EduEnrollment.prepaid_hours > 60))
    elif risk_flag == "非监管账户":
        filters.append(EduPayment.supervision_account_flag == False)
    elif risk_flag == "培训贷":
        filters.append(EduPayment.loan_flag == True)
    elif risk_flag == "未成年人同意缺失":
        filters.append((EduUserInfo.age < 14) & (EduUserInfo.guardian_consent_status != "GRANTED"))
    elif risk_flag == "机构合规异常":
        filters.append((EduInstitution.license_status != "VALID") | (EduInstitution.whitelist_status == "BLACK"))
    elif risk_flag == "正常":
        filters.extend([
            EduEnrollment.prepaid_months <= 3,
            EduEnrollment.prepaid_hours <= 60,
            (EduPayment.supervision_account_flag == True) | (EduPayment.supervision_account_flag.is_(None)),
            (EduPayment.loan_flag == False) | (EduPayment.loan_flag.is_(None)),
            (EduUserInfo.age.is_(None)) | (EduUserInfo.age >= 14) | (EduUserInfo.guardian_consent_status == "GRANTED"),
            EduInstitution.license_status == "VALID",
            EduInstitution.whitelist_status != "BLACK",
        ])

    base = (
        select(
            EduEnrollment.enrollment_id,
            EduEnrollment.user_id,
            EduUserInfo.student_id,
            EduUserInfo.age,
            EduUserInfo.grade,
            EduUserInfo.guardian_consent_status,
            EduCourse.course_name,
            EduCourse.subject_type,
            EduCourse.total_hours,
            EduInstitution.institution_name,
            EduInstitution.license_status,
            EduInstitution.whitelist_status,
            EduEnrollment.prepaid_months,
            EduEnrollment.prepaid_hours,
            EduPayment.pay_amount,
            EduPayment.supervision_account_flag,
            EduPayment.loan_flag,
            EduEnrollment.enrollment_status,
            EduEnrollment.device_fingerprint,
            EduEnrollment.enrolled_at,
        )
        .join(EduUserInfo, EduEnrollment.user_id == EduUserInfo.user_id)
        .join(EduCourse, EduEnrollment.course_id == EduCourse.course_id)
        .join(EduInstitution, EduEnrollment.institution_id == EduInstitution.institution_id)
        .outerjoin(EduPayment, EduEnrollment.enrollment_id == EduPayment.enrollment_id)
        .where(*filters)
    )
    total_stmt = (
        select(func.count())
        .select_from(EduEnrollment)
        .join(EduUserInfo, EduEnrollment.user_id == EduUserInfo.user_id)
        .join(EduCourse, EduEnrollment.course_id == EduCourse.course_id)
        .join(EduInstitution, EduEnrollment.institution_id == EduInstitution.institution_id)
        .outerjoin(EduPayment, EduEnrollment.enrollment_id == EduPayment.enrollment_id)
        .where(*filters)
    )
    total = int((await db.execute(total_stmt)).scalar() or 0)

    stmt = (
        base
        .order_by(EduEnrollment.enrolled_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    items = []
    for row in rows:
        risk_flags = []
        if row.prepaid_months > 3 or row.prepaid_hours > 60:
            risk_flags.append("预收费超限")
        if row.supervision_account_flag is False:
            risk_flags.append("非监管账户")
        if row.loan_flag:
            risk_flags.append("培训贷")
        if row.age is not None and row.age < 14 and row.guardian_consent_status != "GRANTED":
            risk_flags.append("未成年人同意缺失")
        if row.license_status != "VALID" or row.whitelist_status == "BLACK":
            risk_flags.append("机构合规异常")

        items.append({
            "enrollment_id": row.enrollment_id,
            "user_id": row.user_id,
            "student_id": row.student_id,
            "student_name": _student_display_name(row.user_id),
            "age": row.age,
            "grade": row.grade,
            "course_name": row.course_name,
            "subject_type": row.subject_type,
            "total_hours": row.total_hours,
            "institution_name": row.institution_name,
            "prepaid_months": row.prepaid_months,
            "prepaid_hours": row.prepaid_hours,
            "pay_amount": float(row.pay_amount or 0),
            "enrollment_status": row.enrollment_status,
            "device_fingerprint": row.device_fingerprint,
            "enrolled_at": row.enrolled_at.isoformat(sep=" ") if row.enrolled_at else None,
            "risk_flags": risk_flags,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@education_router.get("/students/{user_id}")
async def api_education_student_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db_async),
):
    """学生详情: 汇总学员画像、报名履约、支付退费和风控评估信息。"""
    student = (await db.execute(
        select(EduUserInfo).where(EduUserInfo.user_id == user_id).limit(1)
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail=f"学生不存在: {user_id}")

    same_device_users = 0
    if student.device_fingerprint:
        same_device_users = int((await db.execute(
            select(func.count(func.distinct(EduUserInfo.user_id))).where(
                EduUserInfo.device_fingerprint == student.device_fingerprint,
            )
        )).scalar() or 0)

    enrollment_rows = (await db.execute(
        select(
            EduEnrollment.enrollment_id,
            EduEnrollment.enrollment_status,
            EduEnrollment.prepaid_months,
            EduEnrollment.prepaid_hours,
            EduEnrollment.enrolled_at,
            EduCourse.course_name,
            EduCourse.subject_type,
            EduCourse.total_hours,
            EduInstitution.institution_name,
            EduPayment.pay_amount,
            EduPayment.payment_status,
            EduPayment.supervision_account_flag,
            EduPayment.loan_flag,
        )
        .join(EduCourse, EduEnrollment.course_id == EduCourse.course_id)
        .join(EduInstitution, EduEnrollment.institution_id == EduInstitution.institution_id)
        .outerjoin(EduPayment, EduEnrollment.enrollment_id == EduPayment.enrollment_id)
        .where(EduEnrollment.user_id == user_id)
        .order_by(EduEnrollment.enrolled_at.desc())
        .limit(8)
    )).all()

    payment_count, payment_amount = (await db.execute(
        select(
            func.count(EduPayment.payment_id),
            func.coalesce(func.sum(EduPayment.pay_amount), 0),
        ).where(EduPayment.user_id == user_id)
    )).one()
    refund_count, refund_amount = (await db.execute(
        select(
            func.count(EduRefundRequest.refund_id),
            func.coalesce(func.sum(EduRefundRequest.refund_amount), 0),
        ).where(EduRefundRequest.user_id == user_id)
    )).one()
    progress_count, watch_minutes, avg_completion, last_active_at = (await db.execute(
        select(
            func.count(EduLearningProgress.progress_id),
            func.coalesce(func.sum(EduLearningProgress.watch_minutes), 0),
            func.coalesce(func.avg(EduLearningProgress.completion_rate), 0),
            func.max(EduLearningProgress.last_active_at),
        ).where(EduLearningProgress.user_id == user_id)
    )).one()

    refund_rows = (await db.execute(
        select(
            EduRefundRequest.refund_id,
            EduRefundRequest.refund_reason,
            EduRefundRequest.study_minutes_before_refund,
            EduRefundRequest.refund_amount,
            EduRefundRequest.refund_status,
            EduRefundRequest.applied_at,
        )
        .where(EduRefundRequest.user_id == user_id)
        .order_by(EduRefundRequest.applied_at.desc())
        .limit(5)
    )).all()
    complaint_rows = (await db.execute(
        select(
            EduComplaint.complaint_id,
            EduComplaint.complaint_type,
            EduComplaint.complaint_status,
            EduComplaint.created_at,
        )
        .where(EduComplaint.user_id == user_id)
        .order_by(EduComplaint.created_at.desc())
        .limit(5)
    )).all()
    cert_rows = (await db.execute(
        select(
            EduCertificateVerification.cert_type,
            EduCertificateVerification.cert_verify_source,
            EduCertificateVerification.verify_result,
            EduCertificateVerification.submitted_at,
        )
        .where(EduCertificateVerification.user_id == user_id)
        .order_by(EduCertificateVerification.submitted_at.desc())
        .limit(3)
    )).all()
    assessment_rows = (await db.execute(
        select(
            RiskAssessment.assessment_id,
            RiskEvent.event_type,
            RiskEvent.event_source_id,
            RiskAssessment.final_score,
            RiskAssessment.risk_level,
            RiskAssessment.decision,
            RiskAssessment.rule_count,
            RiskAssessment.create_time,
        )
        .join(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id)
        .where(RiskAssessment.user_id == user_id)
        .order_by(RiskAssessment.create_time.desc())
        .limit(5)
    )).all()

    latest_assessment = assessment_rows[0] if assessment_rows else None
    risk_flags = []
    if any(row.prepaid_months > 3 or row.prepaid_hours > 60 for row in enrollment_rows):
        risk_flags.append("预收费超限")
    if any(row.supervision_account_flag is False for row in enrollment_rows):
        risk_flags.append("非监管账户")
    if any(row.loan_flag for row in enrollment_rows):
        risk_flags.append("培训贷")
    if student.age is not None and student.age < 14 and student.guardian_consent_status != "GRANTED":
        risk_flags.append("未成年人同意缺失")
    if same_device_users >= 5:
        risk_flags.append("共享设备")

    return {
        "student": {
            "user_id": student.user_id,
            "student_id": student.student_id,
            "student_name": _student_display_name(student.user_id),
            "role": student.role,
            "age": student.age,
            "grade": student.grade,
            "real_name_status": student.real_name_status,
            "guardian_consent_status": student.guardian_consent_status,
            "guardian_id": student.guardian_id,
            "device_fingerprint": student.device_fingerprint,
            "same_device_users": same_device_users,
            "ip_region": student.ip_region,
            "register_at": student.register_at.isoformat(sep=" ") if student.register_at else None,
        },
        "summary": {
            "enrollment_count": len(enrollment_rows),
            "payment_count": int(payment_count or 0),
            "payment_amount": float(payment_amount or 0),
            "refund_count": int(refund_count or 0),
            "refund_amount": float(refund_amount or 0),
            "progress_count": int(progress_count or 0),
            "watch_minutes": int(watch_minutes or 0),
            "avg_completion": float(avg_completion or 0),
            "last_active_at": last_active_at.isoformat(sep=" ") if last_active_at else None,
            "latest_score": latest_assessment.final_score if latest_assessment else None,
            "latest_risk_level": latest_assessment.risk_level if latest_assessment else "未评估",
            "latest_decision": latest_assessment.decision if latest_assessment else "未评估",
            "risk_flags": risk_flags,
        },
        "enrollments": [
            {
                "enrollment_id": row.enrollment_id,
                "course_name": row.course_name,
                "subject_type": row.subject_type,
                "total_hours": row.total_hours,
                "institution_name": row.institution_name,
                "prepaid_months": row.prepaid_months,
                "prepaid_hours": row.prepaid_hours,
                "pay_amount": float(row.pay_amount or 0),
                "payment_status": row.payment_status,
                "enrollment_status": row.enrollment_status,
                "enrolled_at": row.enrolled_at.isoformat(sep=" ") if row.enrolled_at else None,
            }
            for row in enrollment_rows
        ],
        "refunds": [
            {
                "refund_id": row.refund_id,
                "refund_reason": row.refund_reason,
                "study_minutes_before_refund": row.study_minutes_before_refund,
                "refund_amount": float(row.refund_amount or 0),
                "refund_status": row.refund_status,
                "applied_at": row.applied_at.isoformat(sep=" ") if row.applied_at else None,
            }
            for row in refund_rows
        ],
        "complaints": [
            {
                "complaint_id": row.complaint_id,
                "complaint_type": row.complaint_type,
                "complaint_status": row.complaint_status,
                "created_at": row.created_at.isoformat(sep=" ") if row.created_at else None,
            }
            for row in complaint_rows
        ],
        "certifications": [
            {
                "cert_type": row.cert_type,
                "cert_verify_source": row.cert_verify_source,
                "verify_result": row.verify_result,
                "submitted_at": row.submitted_at.isoformat(sep=" ") if row.submitted_at else None,
            }
            for row in cert_rows
        ],
        "assessments": [
            {
                "assessment_id": row.assessment_id,
                "event_type": row.event_type,
                "event_source_id": row.event_source_id,
                "final_score": row.final_score,
                "risk_level": row.risk_level,
                "decision": row.decision,
                "rule_count": row.rule_count,
                "create_time": row.create_time.isoformat(sep=" ") if row.create_time else None,
            }
            for row in assessment_rows
        ],
    }


async def _education_features(db: AsyncSession, row) -> dict:
    """为教育报名单计算规则字段, 字段名与 risk_rule.rule_condition 对齐."""
    now = row.enrolled_at or datetime.now()
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)
    since_90d = now - timedelta(days=90)
    pay_amount = float(row.pay_amount or 0)
    account_age_days = (now - row.register_at).days if row.register_at else 9999

    progress_rate = float((await db.execute(
        select(func.coalesce(func.max(EduLearningProgress.completion_rate), 0)).where(
            EduLearningProgress.enrollment_id == row.enrollment_id
        )
    )).scalar() or 0)
    refund_amount = float((await db.execute(
        select(func.coalesce(func.max(EduRefundRequest.refund_amount), 0)).where(
            EduRefundRequest.enrollment_id == row.enrollment_id
        )
    )).scalar() or 0)
    refund_count_30d = int((await db.execute(
        select(func.count()).select_from(EduRefundRequest).where(
            EduRefundRequest.user_id == row.user_id,
            EduRefundRequest.applied_at >= since_30d,
        )
    )).scalar() or 0)
    refund_count_90d = int((await db.execute(
        select(func.count()).select_from(EduRefundRequest).where(
            EduRefundRequest.user_id == row.user_id,
            EduRefundRequest.applied_at >= since_90d,
        )
    )).scalar() or 0)
    refund_total_amount_90d = float((await db.execute(
        select(func.coalesce(func.sum(EduRefundRequest.refund_amount), 0)).where(
            EduRefundRequest.user_id == row.user_id,
            EduRefundRequest.applied_at >= since_90d,
        )
    )).scalar() or 0)
    study_minutes_before_refund_min = int((await db.execute(
        select(func.coalesce(func.min(EduRefundRequest.study_minutes_before_refund), 999999)).where(
            EduRefundRequest.enrollment_id == row.enrollment_id,
        )
    )).scalar() or 999999)
    same_course_new_accounts_7d = int((await db.execute(
        select(func.count(func.distinct(EduEnrollment.user_id)))
        .join(EduUserInfo, EduEnrollment.user_id == EduUserInfo.user_id)
        .where(
            EduEnrollment.course_id == row.course_id,
            EduEnrollment.enrolled_at >= since_7d,
            EduEnrollment.enrolled_at <= now,
            EduUserInfo.register_at >= since_30d,
        )
    )).scalar() or 0)
    same_device_students_7d = int((await db.execute(
        select(func.count(func.distinct(EduEnrollment.user_id))).where(
            EduEnrollment.device_fingerprint == row.device_fingerprint,
            EduEnrollment.enrolled_at >= since_7d,
        )
    )).scalar() or 0) if row.device_fingerprint else 0
    same_device_student_count = int((await db.execute(
        select(func.count(func.distinct(EduUserInfo.user_id))).where(
            EduUserInfo.device_fingerprint == row.device_fingerprint,
            EduUserInfo.role == "STUDENT",
        )
    )).scalar() or 0) if row.device_fingerprint else 0
    pay_amount_sum_1h = float((await db.execute(
        select(func.coalesce(func.sum(EduPayment.pay_amount), 0))
        .join(EduEnrollment, EduPayment.enrollment_id == EduEnrollment.enrollment_id)
        .where(
            EduPayment.user_id == row.user_id,
            EduEnrollment.enrolled_at >= now - timedelta(hours=1),
            EduEnrollment.enrolled_at <= now,
        )
    )).scalar() or 0)
    complete_lesson_count_1h = int((await db.execute(
        select(func.count()).select_from(EduLearningProgress).where(
            EduLearningProgress.user_id == row.user_id,
            EduLearningProgress.enrollment_id == row.enrollment_id,
            EduLearningProgress.last_active_at >= now - timedelta(hours=1),
            EduLearningProgress.completion_rate >= Decimal("0.95"),
        )
    )).scalar() or 0)
    cert_material_reuse = int((await db.execute(
        select(func.count(func.distinct(EduCertificateVerification.user_id)))
        .where(
            EduCertificateVerification.material_hash.in_(
                select(EduCertificateVerification.material_hash).where(
                    EduCertificateVerification.user_id == row.user_id
                )
            )
        )
        .group_by(EduCertificateVerification.material_hash)
        .order_by(func.count(func.distinct(EduCertificateVerification.user_id)).desc())
        .limit(1)
    )).scalar() or 0)
    reward_amount = float((await db.execute(
        select(func.coalesce(func.max(EduLiveReward.reward_amount), 0)).where(
            EduLiveReward.user_id == row.user_id,
            EduLiveReward.course_id == row.course_id,
        )
    )).scalar() or 0)
    account_change_count_30d = int((await db.execute(
        select(func.count()).select_from(EduInstitutionAccountChange).where(
            EduInstitutionAccountChange.institution_id == row.institution_id,
            EduInstitutionAccountChange.changed_at >= since_30d,
        )
    )).scalar() or 0)
    institution_complaint_count_7d = int((await db.execute(
        select(func.count()).select_from(EduComplaint).where(
            EduComplaint.institution_id == row.institution_id,
            EduComplaint.created_at >= since_7d,
        )
    )).scalar() or 0)
    user_enrollment_count = int((await db.execute(
        select(func.count()).select_from(EduEnrollment).where(
            EduEnrollment.user_id == row.user_id,
            EduEnrollment.enrolled_at <= now,
        )
    )).scalar() or 0)
    black_values = [row.user_id]
    if row.student_id:
        black_values.append(row.student_id)
    if row.cert_no_hash:
        black_values.append(row.cert_no_hash)
    blacklisted_identity = int((await db.execute(
        select(func.count()).select_from(RiskBlacklist).where(
            RiskBlacklist.blacklist_value.in_(black_values),
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalar() or 0)

    is_institution_normal = row.license_status == "VALID" and row.whitelist_status != "BLACK"
    course_scene = "周末" if now.weekday() >= 5 else "工作日"
    return {
        "edu_prepaid_months": row.prepaid_months,
        "edu_prepaid_hours": row.prepaid_hours,
        "edu_supervision_account_flag": 1 if row.supervision_account_flag else 0,
        "edu_loan_flag": 1 if row.loan_flag else 0,
        "student_age": row.age or 0,
        "guardian_consent_flag": 1 if row.guardian_consent_status == "GRANTED" else 0,
        "institution_compliance_status": "正常" if is_institution_normal else "异常",
        "course_type": row.subject_type,
        "course_scene": course_scene,
        "same_course_new_accounts_7d": same_course_new_accounts_7d,
        "study_progress_rate": progress_rate,
        "study_minutes_before_refund_min": study_minutes_before_refund_min,
        "refund_amount_rate": refund_amount / pay_amount if pay_amount > 0 else 0,
        "refund_count_30d": refund_count_30d,
        "refund_count_90d": refund_count_90d,
        "refund_total_amount_90d": refund_total_amount_90d,
        "student_count_same_device_7d": same_device_students_7d,
        "same_device_student_count": same_device_student_count,
        "pay_amount_sum_1h": pay_amount_sum_1h,
        "lesson_complete_interval_sec": 999999,
        "complete_lesson_count_1h": complete_lesson_count_1h,
        "same_material_hash_user_count": cert_material_reuse,
        "reward_amount": reward_amount,
        "max_live_reward_amount": reward_amount,
        "account_age_days": account_age_days,
        "account_change_count_30d": account_change_count_30d,
        "institution_complaint_count_7d": institution_complaint_count_7d,
        "user_enrollment_count": user_enrollment_count,
        "teacher_buys_student_core_course": 1 if row.role == "TEACHER" and row.subject_type == "SUBJECT" else 0,
        "blacklisted_identity": 1 if blacklisted_identity else 0,
        "course_amount": pay_amount,
    }


def _score_to_level(score: int) -> str:
    if score >= 85:
        return "极高"
    if score >= 70:
        return "高"
    if score >= 40:
        return "中"
    return "低"


def _score_to_decision(score: int) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    if score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    if score < settings.RISK_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def _education_features_for_xgb(features: dict) -> dict:
    """把教育业务特征映射到当前 XGBoost 模型使用的通用 25 维特征。"""
    enrollment_count = float(features.get("user_enrollment_count", 0) or 0)
    course_amount = float(features.get("course_amount", 0) or 0)
    refund_count = float(features.get("refund_count_90d", 0) or 0)
    refund_amount = float(features.get("refund_total_amount_90d", 0) or 0)
    prepaid_months = float(features.get("edu_prepaid_months", 0) or 0)
    prepaid_hours = float(features.get("edu_prepaid_hours", 0) or 0)
    same_device_count = float(features.get("same_device_student_count", 0) or 0)
    account_age_days = float(features.get("account_age_days", 9999) or 9999)
    account_age_days = max(account_age_days, 0)
    refund_rate = min(refund_count / max(enrollment_count, 1), 1.0)

    return {
        "user_total_orders": enrollment_count,
        "user_orders_30d": enrollment_count,
        "user_orders_7d": float(features.get("same_course_new_accounts_7d", 0) or 0),
        "user_total_amount": max(course_amount, float(features.get("pay_amount_sum_1h", 0) or 0)),
        "user_avg_order_amount": course_amount,
        "user_max_order_amount": course_amount,
        "user_refund_count": refund_count,
        "user_postsale_count": float(features.get("refund_count_30d", 0) or 0),
        "user_refund_rate": max(refund_rate, float(features.get("refund_amount_rate", 0) or 0)),
        "user_postsale_rate": refund_rate,
        "user_refund_amount": refund_amount,
        "user_cancel_count": 1 if features.get("study_minutes_before_refund_min", 999999) < 5 else 0,
        "user_complaint_count": float(features.get("institution_complaint_count_7d", 0) or 0),
        "user_address_count": same_device_count,
        "order_total_amount": course_amount,
        "order_item_count": max(prepaid_hours, 1),
        "order_sku_count": max(prepaid_months, 1),
        "order_discount_amount": 0,
        "order_discount_rate": 0,
        "order_pay_interval_sec": min(account_age_days * 86400, 365 * 86400),
        "order_is_night": 0,
        "order_category_count": 2 if features.get("course_type") == "SUBJECT" else 1,
        "addr_total_count": same_device_count,
        "addr_province_count": float(features.get("student_count_same_device_7d", 0) or 0),
        "addr_is_new": 1 if account_age_days < 30 or features.get("blacklisted_identity") else 0,
    }


def _calculate_education_decision(hits: list[dict], features: dict) -> tuple[int, str, str, float | None, str | None]:
    """教育链路规则 + XGBoost 双轨融合。极高/拒绝规则保持一票否决。"""
    rule_score = min((max((h["risk_score"] for h in hits), default=18) + max(len(hits) - 1, 0) * 3), 100)
    has_veto = any(h["risk_level"] == "极高" or h["action"] == "拒绝" for h in hits)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    ml_score = None
    ml_decision = None
    if is_model_loaded():
        ml_result = predict(_education_features_for_xgb(features))
        if ml_result.is_loaded:
            ml_score = ml_result.score
            ml_decision = ml_result.decision

    if ml_score is not None:
        ml_score_100 = _ml_prob_to_risk_score(ml_score)
        final_score = int(round(
            settings.ML_WEIGHT_RULE * rule_score
            + settings.ML_WEIGHT_XGB * ml_score_100
        ))
        final_score = max(0, min(100, final_score))
    else:
        final_score = rule_score

    risk_level = _score_to_level(final_score)
    decision = _score_to_decision(final_score)
    if has_veto:
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)
        risk_level = "极高"
        decision = "拒绝"
    return final_score, risk_level, decision, ml_score, ml_decision


def is_education_risk_request(request: RiskCheckRequest) -> bool:
    """判断风险检查请求是否属于教育业务。"""
    return (
        request.event_type in {
            "课程报名", "支付成功", "学习行为", "退费申请",
            "投诉提交", "证书核验", "直播打赏", "机构账户变更",
        }
        or request.source_id.startswith(("EENR", "EPAY", "EREF", "ECMP", "ECER", "ERWD"))
        or request.user_id.startswith(("ESTU", "EGU", "ETU"))
    )


def _education_enrollment_select():
    return (
        select(
            EduEnrollment.enrollment_id,
            EduEnrollment.user_id,
            EduEnrollment.course_id,
            EduEnrollment.institution_id,
            EduEnrollment.prepaid_months,
            EduEnrollment.prepaid_hours,
            EduEnrollment.device_fingerprint,
            EduEnrollment.ip_region,
            EduEnrollment.enrolled_at,
            EduUserInfo.role,
            EduUserInfo.student_id,
            EduUserInfo.cert_no_hash,
            EduUserInfo.register_at,
            EduUserInfo.age,
            EduUserInfo.grade,
            EduUserInfo.guardian_consent_status,
            EduCourse.course_name,
            EduCourse.subject_type,
            EduCourse.total_hours,
            EduInstitution.institution_name,
            EduInstitution.license_status,
            EduInstitution.whitelist_status,
            EduPayment.pay_amount,
            EduPayment.supervision_account_flag,
            EduPayment.loan_flag,
        )
        .join(EduUserInfo, EduEnrollment.user_id == EduUserInfo.user_id)
        .join(EduCourse, EduEnrollment.course_id == EduCourse.course_id)
        .join(EduInstitution, EduEnrollment.institution_id == EduInstitution.institution_id)
        .outerjoin(EduPayment, EduEnrollment.enrollment_id == EduPayment.enrollment_id)
    )


async def process_education_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """教育行业单笔重做检查: 使用 risk_rule 表中的教育规则实时评估。"""
    row = (await db.execute(
        _education_enrollment_select().where(
            EduEnrollment.enrollment_id == request.source_id,
            EduEnrollment.user_id == request.user_id,
        ).limit(1)
    )).first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"教育报名单不存在或不属于该用户: {request.source_id}",
        )

    event_type = request.event_type if request.event_type in {
        "课程报名", "支付成功", "学习行为", "退费申请",
        "投诉提交", "证书核验", "直播打赏", "机构账户变更",
    } else "课程报名"
    features = await _education_features(db, row)
    matched_rules = match_rules(await load_enabled_rules(db, event_type), features)
    hits = [hit.to_dict() for hit in matched_rules]
    final_score, risk_level, decision, ml_score, ml_decision = _calculate_education_decision(hits, features)

    event_id = _risk_id("evt")
    assessment_id = _risk_id("ast")
    event_data = {
        "industry": "education",
        "business_event_type": event_type,
        "enrollment_id": row.enrollment_id,
        "course_name": row.course_name,
        "institution_name": row.institution_name,
        "student": {"age": row.age, "grade": row.grade},
        "pay_amount": float(row.pay_amount or 0),
        "risk_flags": [h["rule_name"] for h in hits],
        "ml_score": ml_score,
        "ml_decision": ml_decision,
        "features": features,
    }

    db.add(RiskEvent(
        event_id=event_id,
        event_type=event_type,
        event_source_id=row.enrollment_id,
        user_id=row.user_id,
        event_data=json.dumps(event_data, ensure_ascii=False),
    ))
    db.add(RiskAssessment(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=row.user_id,
        rule_results=json.dumps(hits, ensure_ascii=False),
        rule_count=len(hits),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=Decimal(str(ml_score)) if ml_score is not None else None,
        ml_decision=ml_decision,
    ))
    for name in ("edu_prepaid_months", "edu_prepaid_hours", "edu_pay_amount"):
        value = features.get(name, float(row.pay_amount or 0) if name == "edu_pay_amount" else 0)
        db.add(RiskFeature(
            event_id=event_id,
            entity_type="订单",
            entity_id=row.enrollment_id,
            feature_name=name,
            feature_value=Decimal(str(value)),
        ))

    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == row.user_id)
    )).scalar_one_or_none()
    if not profile:
        profile = RiskUserProfile(user_id=row.user_id)
        db.add(profile)
    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()

    if decision in ("人工审核", "拒绝"):
        is_rejected = decision == "拒绝"
        db.add(RiskCase(
            case_id=_risk_id("cas"),
            assessment_id=assessment_id,
            user_id=row.user_id,
            case_status="已拒绝" if is_rejected else "待审核",
            case_category=hits[0]["rule_category"] if hits else "XGBoost模型高风险",
            risk_detail=json.dumps(hits, ensure_ascii=False),
            reviewer="system" if is_rejected else None,
            review_comment="系统自动拒绝: 风险等级达到极高" if is_rejected else None,
            review_time=datetime.now() if is_rejected else None,
            source_id=row.enrollment_id,
            event_type=event_type,
            create_time=datetime.now(),
            update_time=datetime.now(),
        ))

    await db.commit()
    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=row.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(hits),
        triggered_rules=[RuleHitInfo(**h) for h in hits],
        features=features,
        create_time=datetime.now(),
        ml_score=ml_score,
        ml_decision=ml_decision,
    )


async def auto_assess_new_enrollments(
    db: AsyncSession,
    *,
    limit: int = 500,
    enrollment_ids: list[str] | None = None,
    event_type_map: dict[str, str] | None = None,
) -> dict:
    """自动评估尚未进入 risk_assessment 的教育报名单。"""
    valid_event_types = {
        "课程报名", "支付成功", "学习行为", "退费申请",
        "投诉提交", "证书核验", "直播打赏", "机构账户变更",
    }
    stmt = _education_enrollment_select()
    if enrollment_ids:
        stmt = stmt.where(EduEnrollment.enrollment_id.in_(enrollment_ids))
    else:
        stmt = stmt.order_by(EduEnrollment.enrolled_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()

    created_assessments = 0
    created_cases = 0
    skipped = 0
    event_type_counts: dict[str, int] = {}
    rules_cache: dict[str, list] = {}

    for row in rows:
        exists = (await db.execute(
            select(RiskAssessment.assessment_id)
            .join(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id)
            .where(
                RiskEvent.event_source_id == row.enrollment_id,
                RiskEvent.user_id == row.user_id,
            )
            .limit(1)
        )).scalar_one_or_none()
        if exists:
            skipped += 1
            continue

        event_type = (event_type_map or {}).get(row.enrollment_id, "课程报名")
        if event_type not in valid_event_types:
            event_type = "课程报名"
        if event_type not in rules_cache:
            rules_cache[event_type] = await load_enabled_rules(db, event_type)
        enabled_rules = rules_cache[event_type]

        features = await _education_features(db, row)
        matched_rules = match_rules(enabled_rules, features)
        hits = [hit.to_dict() for hit in matched_rules]
        final_score, risk_level, decision, ml_score, ml_decision = _calculate_education_decision(hits, features)

        event_id = _risk_id("evt")
        assessment_id = _risk_id("ast")
        event_time = row.enrolled_at or datetime.now()
        event_data = {
            "industry": "education",
            "business_event_type": event_type,
            "enrollment_id": row.enrollment_id,
            "course_name": row.course_name,
            "institution_name": row.institution_name,
            "student": {"age": row.age, "grade": row.grade},
            "prepaid_months": row.prepaid_months,
            "prepaid_hours": row.prepaid_hours,
            "pay_amount": float(row.pay_amount or 0),
            "risk_flags": [h["rule_name"] for h in hits],
            "ml_score": ml_score,
            "ml_decision": ml_decision,
            "features": features,
        }

        db.add(RiskEvent(
            event_id=event_id,
            event_type=event_type,
            event_source_id=row.enrollment_id,
            user_id=row.user_id,
            event_data=json.dumps(event_data, ensure_ascii=False),
            create_time=event_time,
        ))
        db.add(RiskAssessment(
            assessment_id=assessment_id,
            event_id=event_id,
            user_id=row.user_id,
            rule_results=json.dumps(hits, ensure_ascii=False),
            rule_count=len(hits),
            final_score=final_score,
            risk_level=risk_level,
            decision=decision,
            ml_score=Decimal(str(ml_score)) if ml_score is not None else None,
            ml_decision=ml_decision,
            create_time=event_time,
        ))
        db.add(RiskFeature(
            event_id=event_id,
            entity_type="用户",
            entity_id=row.user_id,
            feature_name="edu_prepaid_months",
            feature_value=Decimal(str(row.prepaid_months)),
        ))
        db.add(RiskFeature(
            event_id=event_id,
            entity_type="订单",
            entity_id=row.enrollment_id,
            feature_name="edu_prepaid_hours",
            feature_value=Decimal(str(row.prepaid_hours)),
        ))
        db.add(RiskFeature(
            event_id=event_id,
            entity_type="订单",
            entity_id=row.enrollment_id,
            feature_name="edu_pay_amount",
            feature_value=Decimal(str(float(row.pay_amount or 0))),
        ))

        profile = (await db.execute(
            select(RiskUserProfile).where(RiskUserProfile.user_id == row.user_id)
        )).scalar_one_or_none()
        if not profile:
            profile = RiskUserProfile(user_id=row.user_id)
            db.add(profile)
        profile.risk_score = final_score
        profile.risk_level = risk_level
        profile.assessment_count = (profile.assessment_count or 0) + 1
        profile.last_assessment_time = event_time
        profile.profile_data = json.dumps({
            "industry": "education",
            "grade": row.grade,
            "course_name": row.course_name,
            "institution_name": row.institution_name,
        }, ensure_ascii=False)

        if decision in ("人工审核", "拒绝"):
            is_rejected = decision == "拒绝"
            db.add(RiskCase(
                case_id=_risk_id("cas"),
                assessment_id=assessment_id,
                user_id=row.user_id,
                case_status="已拒绝" if is_rejected else "待审核",
                case_category=hits[0]["rule_category"] if hits else "XGBoost模型高风险",
                risk_detail=json.dumps(hits, ensure_ascii=False),
                reviewer="system" if is_rejected else None,
                review_comment="系统自动拒绝: 风险等级达到极高" if is_rejected else None,
                review_time=datetime.now() if is_rejected else None,
                source_id=row.enrollment_id,
                event_type=event_type,
                create_time=datetime.now(),
                update_time=datetime.now(),
            ))
            created_cases += 1
        created_assessments += 1
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

    if created_assessments:
        await db.commit()
    return {
        "created_assessments": created_assessments,
        "created_cases": created_cases,
        "skipped": skipped,
        "total_scanned": len(rows),
        "event_type_counts": event_type_counts,
    }


@education_router.post("/generate-risk-assessments")
async def api_generate_education_risk_assessments(
    limit: int = Query(120, ge=1, le=500),
    db: AsyncSession = Depends(get_db_async),
):
    """兼容旧按钮调用: 实际已经改为自动补评。"""
    return await auto_assess_new_enrollments(db, limit=limit)
