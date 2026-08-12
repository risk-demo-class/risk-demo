"""
教育行业风控系统 - 业务数据生成脚本

默认生成 120 条报名主数据, 并连带生成用户、机构、课程、支付、学习、
退款、投诉、认证、打赏、设备等教育行业业务表数据。

用法:
  python scripts/gen_education_business_data.py
  python scripts/gen_education_business_data.py --count 200
  python scripts/gen_education_business_data.py --clear --count 120
"""
import argparse
import asyncio
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal, async_engine
    from app.models_business import (
        EduCertificateVerification,
        EduComplaint,
        EduContract,
        EduCourse,
        EduDeviceBinding,
        EduEnrollment,
        EduInstitution,
        EduInstitutionAccountChange,
        EduLearningProgress,
        EduLesson,
        EduLiveReward,
        EduPayment,
        EduRefundRequest,
        EduTeacher,
        EduUserInfo,
    )
    DB_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    delete = None
    AsyncSessionLocal = None
    async_engine = None
    DB_IMPORT_ERROR = exc

    class _PlainRow:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def _row_class(name: str):
        return type(name, (_PlainRow,), {})

    EduCertificateVerification = _row_class("EduCertificateVerification")
    EduComplaint = _row_class("EduComplaint")
    EduContract = _row_class("EduContract")
    EduCourse = _row_class("EduCourse")
    EduDeviceBinding = _row_class("EduDeviceBinding")
    EduEnrollment = _row_class("EduEnrollment")
    EduInstitution = _row_class("EduInstitution")
    EduInstitutionAccountChange = _row_class("EduInstitutionAccountChange")
    EduLearningProgress = _row_class("EduLearningProgress")
    EduLesson = _row_class("EduLesson")
    EduLiveReward = _row_class("EduLiveReward")
    EduPayment = _row_class("EduPayment")
    EduRefundRequest = _row_class("EduRefundRequest")
    EduTeacher = _row_class("EduTeacher")
    EduUserInfo = _row_class("EduUserInfo")


EDU_TABLES_IN_ORDER = [
    EduInstitution,
    EduUserInfo,
    EduTeacher,
    EduCourse,
    EduEnrollment,
    EduContract,
    EduPayment,
    EduLesson,
    EduLearningProgress,
    EduRefundRequest,
    EduComplaint,
    EduCertificateVerification,
    EduLiveReward,
    EduDeviceBinding,
    EduInstitutionAccountChange,
]

TABLE_COLUMNS = {
    "institutions": ("edu_institution", [
        "institution_id", "institution_name", "license_no", "license_status",
        "whitelist_status", "supervision_account_no", "province", "city", "created_at",
    ]),
    "users": ("edu_user_info", [
        "user_id", "role", "student_id", "name_hash", "cert_no_hash", "age", "grade",
        "guardian_id", "real_name_status", "guardian_consent_status", "device_fingerprint",
        "ip_region", "register_at",
    ]),
    "teachers": ("edu_teacher", [
        "teacher_id", "user_id", "institution_id", "qualification_no_hash",
        "qualification_status", "subject_scope", "hired_at",
    ]),
    "courses": ("edu_course", [
        "course_id", "institution_id", "teacher_id", "course_name", "subject_type",
        "training_type", "delivery_mode", "total_hours", "price", "published_status",
        "content_risk_label", "created_at",
    ]),
    "enrollments": ("edu_enrollment", [
        "enrollment_id", "user_id", "course_id", "institution_id", "study_goal",
        "expected_finish_days", "enrollment_status", "prepaid_months", "prepaid_hours",
        "device_fingerprint", "ip_region", "enrolled_at",
    ]),
    "contracts": ("edu_contract", [
        "contract_id", "enrollment_id", "contract_version", "standard_template_flag",
        "sign_channel", "contract_status", "signed_at",
    ]),
    "payments": ("edu_payment", [
        "payment_id", "enrollment_id", "user_id", "payer_id", "pay_amount", "pay_channel",
        "payment_account_type", "payment_account_hash", "supervision_account_flag",
        "loan_flag", "payment_status", "paid_at",
    ]),
    "lessons": ("edu_lesson", [
        "lesson_id", "course_id", "teacher_id", "lesson_title", "scheduled_start_at",
        "scheduled_end_at", "delivery_mode",
    ]),
    "progress": ("edu_learning_progress", [
        "progress_id", "enrollment_id", "user_id", "course_id", "lesson_id",
        "watch_minutes", "interaction_count", "completion_rate", "device_fingerprint",
        "ip_region", "last_active_at",
    ]),
    "refunds": ("edu_refund_request", [
        "refund_id", "enrollment_id", "payment_id", "user_id", "refund_reason",
        "study_minutes_before_refund", "consumed_hours", "refund_amount", "refund_status",
        "applied_at", "reviewed_at",
    ]),
    "complaints": ("edu_complaint", [
        "complaint_id", "user_id", "institution_id", "enrollment_id", "complaint_type",
        "complaint_status", "content_summary", "created_at", "closed_at",
    ]),
    "certs": ("edu_certificate_verification", [
        "cert_id", "user_id", "cert_type", "cert_verify_source", "material_hash",
        "verify_result", "submitted_at", "verified_at",
    ]),
    "rewards": ("edu_live_reward", [
        "reward_id", "live_session_id", "user_id", "course_id", "teacher_id",
        "reward_amount", "reward_status", "paid_at",
    ]),
    "bindings": ("edu_device_binding", [
        "binding_id", "user_id", "device_fingerprint", "device_type", "ip_region",
        "bind_channel", "first_seen_at", "last_seen_at",
    ]),
    "account_changes": ("edu_institution_account_change", [
        "change_id", "institution_id", "old_account_hash", "new_account_hash",
        "account_type", "change_reason", "changed_at",
    ]),
}


PROVINCES = [
    ("北京", "北京"),
    ("上海", "上海"),
    ("广东", "深圳"),
    ("浙江", "杭州"),
    ("四川", "成都"),
    ("湖北", "武汉"),
]
GRADES = ["幼小衔接", "小学三年级", "小学六年级", "初一", "初三", "高一", "高三"]
SUBJECT_COURSES = ["数学思维提升", "英语阅读精讲", "语文写作训练", "物理同步强化"]
NON_SUBJECT_COURSES = ["机器人编程", "少儿美术", "篮球体能", "科学实验"]
DEVICE_POOL = [f"DEV-SHARED-{i:02d}" for i in range(1, 9)] + [f"DEV-NORMAL-{i:03d}" for i in range(1, 80)]
IP_REGIONS = ["北京-朝阳", "上海-浦东", "广东-深圳", "浙江-杭州", "四川-成都", "湖北-武汉"]
PAY_CHANNELS = ["WECHAT", "ALIPAY", "BANK_CARD", "PUBLIC_PLATFORM"]
STUDY_GOALS = ["升学备考", "兴趣拓展", "补齐基础", "竞赛准备", "托管陪伴"]
REFUND_REASONS = ["课程不匹配", "时间冲突", "退费难投诉", "领取资料后退款", "老师更换"]
COMPLAINT_TYPES = ["REFUND_DIFFICULT", "FALSE_MARKETING", "PRIVATE_PAYMENT", "COURSE_QUALITY"]
EDUCATION_EVENT_TYPES = [
    "课程报名",
    "支付成功",
    "学习行为",
    "退费申请",
    "投诉提交",
    "证书核验",
    "直播打赏",
    "机构账户变更",
]
EDUCATION_EVENT_TYPE_WEIGHTS = [28, 22, 16, 12, 8, 5, 5, 4]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _money(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def _id(prefix: str, batch: str, idx: int) -> str:
    return f"{prefix}{batch}{idx:04d}"


def _pick_time(days_back: int = 90) -> datetime:
    return datetime.now() - timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


def build_random_event_type_map(enrollments: list) -> dict[str, str]:
    """为本批报名数据随机分配教育行业事件类型, 并保证小批量也覆盖多种事件。"""
    enrollment_ids = [row.enrollment_id for row in enrollments]
    if not enrollment_ids:
        return {}

    seed_types = EDUCATION_EVENT_TYPES.copy()
    random.shuffle(seed_types)
    event_types: list[str] = []
    for idx in range(len(enrollment_ids)):
        if idx < len(seed_types):
            event_types.append(seed_types[idx])
        else:
            event_types.append(
                random.choices(
                    EDUCATION_EVENT_TYPES,
                    weights=EDUCATION_EVENT_TYPE_WEIGHTS,
                    k=1,
                )[0]
            )
    random.shuffle(event_types)
    return dict(zip(enrollment_ids, event_types))


async def ensure_tables() -> None:
    """只创建教育业务表, 不触碰已有电商/风控表。"""
    if async_engine is None:
        raise RuntimeError(f"当前 Python 环境缺少数据库依赖: {DB_IMPORT_ERROR}")
    async with async_engine.begin() as conn:
        for model in EDU_TABLES_IN_ORDER:
            await conn.run_sync(lambda sync_conn, m=model: m.__table__.create(sync_conn, checkfirst=True))


async def clear_education_tables() -> None:
    if AsyncSessionLocal is None or delete is None:
        raise RuntimeError(f"当前 Python 环境缺少数据库依赖: {DB_IMPORT_ERROR}")
    async with AsyncSessionLocal() as db:
        for model in reversed(EDU_TABLES_IN_ORDER):
            await db.execute(delete(model))
        await db.commit()


def build_dataset(enrollment_count: int, batch: str) -> dict[str, list]:
    now = datetime.now()
    institution_count = 6
    teacher_count = 12
    guardian_count = max(20, enrollment_count // 4)
    student_count = max(enrollment_count, 100)
    course_count = 24

    institutions = []
    for i in range(1, institution_count + 1):
        province, city = PROVINCES[(i - 1) % len(PROVINCES)]
        risky = i in (5, 6)
        institutions.append(EduInstitution(
            institution_id=_id("EINST", batch, i),
            institution_name=f"未来课堂教育中心{i}",
            license_no=None if risky and i == 6 else f"EDU-LIC-{batch}-{i:03d}",
            license_status="MISSING" if i == 6 else ("EXPIRED" if i == 5 else "VALID"),
            whitelist_status="BLACK" if i == 6 else ("GRAY" if i == 5 else "WHITE"),
            supervision_account_no=None if risky else f"SUP-{batch}-{i:03d}",
            province=province,
            city=city,
            created_at=now - timedelta(days=365 + i),
        ))

    guardians = []
    for i in range(1, guardian_count + 1):
        device = random.choice(DEVICE_POOL)
        guardians.append(EduUserInfo(
            user_id=_id("EGU", batch, i),
            role="GUARDIAN",
            student_id=None,
            name_hash=_hash(f"guardian-{batch}-{i}"),
            cert_no_hash=_hash(f"guardian-cert-{batch}-{i}"),
            age=random.randint(30, 52),
            grade=None,
            guardian_id=None,
            real_name_status=random.choices(["VERIFIED", "PENDING"], weights=[92, 8])[0],
            guardian_consent_status="NOT_REQUIRED",
            device_fingerprint=device,
            ip_region=random.choice(IP_REGIONS),
            register_at=_pick_time(180),
        ))

    students = []
    for i in range(1, student_count + 1):
        guardian = guardians[(i - 1) % len(guardians)]
        is_minor = random.random() < 0.88
        age = random.randint(6, 17) if is_minor else random.randint(18, 24)
        shared_device = random.choice(DEVICE_POOL[:5]) if i <= max(10, student_count // 8) else random.choice(DEVICE_POOL)
        students.append(EduUserInfo(
            user_id=_id("ESTU", batch, i),
            role="STUDENT",
            student_id=f"STU-{batch}-{i:05d}",
            name_hash=_hash(f"student-{batch}-{i}"),
            cert_no_hash=_hash(f"student-cert-{batch}-{i}"),
            age=age,
            grade=random.choice(GRADES),
            guardian_id=guardian.user_id if is_minor else None,
            real_name_status=random.choices(["VERIFIED", "PENDING", "FAILED"], weights=[86, 10, 4])[0],
            guardian_consent_status=random.choices(["GRANTED", "MISSING"], weights=[90, 10])[0] if is_minor else "NOT_REQUIRED",
            device_fingerprint=shared_device,
            ip_region=random.choice(IP_REGIONS),
            register_at=_pick_time(180),
        ))

    teacher_users = []
    teachers = []
    for i in range(1, teacher_count + 1):
        inst = institutions[(i - 1) % len(institutions)]
        user_id = _id("ETU", batch, i)
        teacher_users.append(EduUserInfo(
            user_id=user_id,
            role="TEACHER",
            student_id=None,
            name_hash=_hash(f"teacher-{batch}-{i}"),
            cert_no_hash=_hash(f"teacher-cert-{batch}-{i}"),
            age=random.randint(24, 48),
            grade=None,
            guardian_id=None,
            real_name_status="VERIFIED",
            guardian_consent_status="NOT_REQUIRED",
            device_fingerprint=random.choice(DEVICE_POOL),
            ip_region=random.choice(IP_REGIONS),
            register_at=_pick_time(300),
        ))
        teachers.append(EduTeacher(
            teacher_id=_id("ETEA", batch, i),
            user_id=user_id,
            institution_id=inst.institution_id,
            qualification_no_hash=_hash(f"qualification-{batch}-{i}"),
            qualification_status=random.choices(["VERIFIED", "PENDING", "FAILED"], weights=[82, 12, 6])[0],
            subject_scope=random.choice(["数学", "英语", "语文", "科学", "艺术", "体育", "编程"]),
            hired_at=_pick_time(360),
        ))

    users = guardians + students + teacher_users

    courses = []
    for i in range(1, course_count + 1):
        teacher = teachers[(i - 1) % len(teachers)]
        is_subject = random.random() < 0.45
        name = random.choice(SUBJECT_COURSES if is_subject else NON_SUBJECT_COURSES)
        hours = random.choice([16, 24, 32, 48, 60, 72, 96])
        base_price = random.choice([1299, 1999, 2999, 3999, 4999, 6999, 9999])
        courses.append(EduCourse(
            course_id=_id("ECRS", batch, i),
            institution_id=teacher.institution_id,
            teacher_id=teacher.teacher_id,
            course_name=f"{name}{i}",
            subject_type="SUBJECT" if is_subject else "NON_SUBJECT",
            training_type=random.choice(["ONLINE", "OFFLINE", "HYBRID"]),
            delivery_mode=random.choice(["LIVE", "RECORDED", "CLASSROOM"]),
            total_hours=hours,
            price=_money(base_price),
            published_status=random.choices(["PUBLISHED", "REVIEWING", "SUSPENDED"], weights=[82, 12, 6])[0],
            content_risk_label=random.choices([None, "HIDDEN_SUBJECT", "GUARANTEE_PASS"], weights=[86, 8, 6])[0],
            created_at=_pick_time(240),
        ))

    enrollments = []
    contracts = []
    payments = []
    for i in range(1, enrollment_count + 1):
        student = students[(i - 1) % len(students)]
        course = random.choice(courses)
        enrolled_at = _pick_time(90)
        risky_prepaid = random.random() < 0.15
        prepaid_months = random.choice([4, 6, 12]) if risky_prepaid else random.choice([1, 2, 3])
        prepaid_hours = random.choice([72, 96, 120]) if risky_prepaid else min(course.total_hours, random.choice([16, 24, 32, 48, 60]))
        enrollments.append(EduEnrollment(
            enrollment_id=_id("EENR", batch, i),
            user_id=student.user_id,
            course_id=course.course_id,
            institution_id=course.institution_id,
            study_goal=random.choice(STUDY_GOALS),
            expected_finish_days=random.choice([30, 45, 60, 90, 120]),
            enrollment_status=random.choices(["ACTIVE", "COMPLETED", "CANCELLED"], weights=[76, 16, 8])[0],
            prepaid_months=prepaid_months,
            prepaid_hours=prepaid_hours,
            device_fingerprint=student.device_fingerprint,
            ip_region=student.ip_region,
            enrolled_at=enrolled_at,
        ))
        contracts.append(EduContract(
            contract_id=_id("ECON", batch, i),
            enrollment_id=_id("EENR", batch, i),
            contract_version="MOE-DEMO-2021",
            standard_template_flag=random.random() > 0.08,
            sign_channel=random.choice(["APP", "WEB", "OFFLINE"]),
            contract_status=random.choices(["SIGNED", "PENDING"], weights=[90, 10])[0],
            signed_at=enrolled_at + timedelta(minutes=random.randint(1, 120)),
        ))
        private_or_loan = random.random() < 0.12 or prepaid_months > 3 or prepaid_hours > 60
        payer_id = student.guardian_id or student.user_id
        payments.append(EduPayment(
            payment_id=_id("EPAY", batch, i),
            enrollment_id=_id("EENR", batch, i),
            user_id=student.user_id,
            payer_id=payer_id,
            pay_amount=course.price,
            pay_channel=random.choice(PAY_CHANNELS),
            payment_account_type="PRIVATE" if private_or_loan and random.random() < 0.45 else "SUPERVISION",
            payment_account_hash=_hash(f"pay-account-{payer_id}-{random.randint(1, 8)}"),
            supervision_account_flag=not private_or_loan,
            loan_flag=private_or_loan and random.random() < 0.35,
            payment_status=random.choices(["SUCCESS", "PENDING", "FAILED"], weights=[90, 7, 3])[0],
            paid_at=enrolled_at + timedelta(minutes=random.randint(5, 180)),
        ))

    lessons = []
    lesson_idx = 1
    for course in courses:
        teacher_id = course.teacher_id
        for n in range(1, 4):
            start = now + timedelta(days=random.randint(1, 60), hours=random.randint(8, 20))
            lessons.append(EduLesson(
                lesson_id=_id("ELES", batch, lesson_idx),
                course_id=course.course_id,
                teacher_id=teacher_id,
                lesson_title=f"{course.course_name}-第{n}讲",
                scheduled_start_at=start,
                scheduled_end_at=start + timedelta(minutes=90),
                delivery_mode=course.delivery_mode,
            ))
            lesson_idx += 1

    lessons_by_course: dict[str, list[EduLesson]] = {}
    for lesson in lessons:
        lessons_by_course.setdefault(lesson.course_id, []).append(lesson)

    progress_rows = []
    for i, enr in enumerate(enrollments, 1):
        rows_per_enrollment = random.choice([1, 2, 3])
        for n in range(rows_per_enrollment):
            lesson = random.choice(lessons_by_course[enr.course_id])
            watch = random.choices([0, 3, 8, 30, 60, 90, 120], weights=[4, 8, 10, 30, 25, 18, 5])[0]
            progress_rows.append(EduLearningProgress(
                progress_id=f"EPRO{batch}{i:04d}{n:02d}",
                enrollment_id=enr.enrollment_id,
                user_id=enr.user_id,
                course_id=enr.course_id,
                lesson_id=lesson.lesson_id,
                watch_minutes=watch,
                interaction_count=0 if watch < 5 else random.randint(0, 12),
                completion_rate=_money(min(watch / 90, 1)),
                device_fingerprint=enr.device_fingerprint,
                ip_region=enr.ip_region,
                last_active_at=enr.enrolled_at + timedelta(days=random.randint(0, 30), minutes=random.randint(1, 300)),
            ))

    refunds = []
    refund_candidates = random.sample(enrollments, k=max(10, enrollment_count // 4))
    for i, enr in enumerate(refund_candidates, 1):
        payment = payments[int(enr.enrollment_id[-4:]) - 1]
        low_study = random.random() < 0.45
        study_minutes = random.randint(0, 5) if low_study else random.randint(30, 600)
        refunds.append(EduRefundRequest(
            refund_id=_id("EREF", batch, i),
            enrollment_id=enr.enrollment_id,
            payment_id=payment.payment_id,
            user_id=enr.user_id,
            refund_reason=random.choice(REFUND_REASONS),
            study_minutes_before_refund=study_minutes,
            consumed_hours=_money(study_minutes / 60),
            refund_amount=_money(float(payment.pay_amount) * random.uniform(0.35, 1.0)),
            refund_status=random.choices(["APPLIED", "APPROVED", "REJECTED", "MANUAL_REVIEW"], weights=[22, 50, 12, 16])[0],
            applied_at=enr.enrolled_at + timedelta(days=random.randint(1, 45)),
            reviewed_at=enr.enrolled_at + timedelta(days=random.randint(2, 50)),
        ))

    complaints = []
    complaint_candidates = random.sample(enrollments, k=max(8, enrollment_count // 8))
    for i, enr in enumerate(complaint_candidates, 1):
        created = enr.enrolled_at + timedelta(days=random.randint(2, 60))
        complaints.append(EduComplaint(
            complaint_id=_id("ECMP", batch, i),
            user_id=enr.user_id,
            institution_id=enr.institution_id,
            enrollment_id=enr.enrollment_id,
            complaint_type=random.choice(COMPLAINT_TYPES),
            complaint_status=random.choice(["OPEN", "PROCESSING", "CLOSED"]),
            content_summary="家长反馈课程、退费或收费账户存在异常, 需人工核验。",
            created_at=created,
            closed_at=created + timedelta(days=random.randint(1, 12)),
        ))

    certs = []
    cert_users = random.sample(users, k=min(len(users), max(40, enrollment_count // 2)))
    reused_hash = _hash(f"reused-material-{batch}")
    for i, user in enumerate(cert_users, 1):
        certs.append(EduCertificateVerification(
            cert_id=_id("ECER", batch, i),
            user_id=user.user_id,
            cert_type="TEACHER_QUALIFICATION" if user.role == "TEACHER" else "STUDENT_IDENTITY",
            cert_verify_source=random.choice(["OCR", "GOV_API", "MANUAL"]),
            material_hash=reused_hash if i <= 5 else _hash(f"material-{batch}-{user.user_id}"),
            verify_result=random.choices(["PASS", "PENDING", "FAIL"], weights=[84, 10, 6])[0],
            submitted_at=_pick_time(120),
            verified_at=_pick_time(110),
        ))

    rewards = []
    live_courses = [c for c in courses if c.delivery_mode == "LIVE"] or courses
    for i in range(1, max(15, enrollment_count // 6) + 1):
        course = random.choice(live_courses)
        amount = random.choice([9, 19, 66, 199, 599, 1999, 5999])
        student = random.choice(students)
        rewards.append(EduLiveReward(
            reward_id=_id("ERWD", batch, i),
            live_session_id=f"LIVE-{batch}-{random.randint(1, 8):03d}",
            user_id=student.user_id,
            course_id=course.course_id,
            teacher_id=course.teacher_id,
            reward_amount=_money(amount),
            reward_status="SUCCESS",
            paid_at=_pick_time(60),
        ))

    bindings = []
    for i, user in enumerate(users, 1):
        first_seen = user.register_at
        bindings.append(EduDeviceBinding(
            binding_id=_id("EDEV", batch, i),
            user_id=user.user_id,
            device_fingerprint=user.device_fingerprint or random.choice(DEVICE_POOL),
            device_type=random.choice(["ANDROID", "IOS", "WEB", "TABLET"]),
            ip_region=user.ip_region,
            bind_channel=random.choice(["REGISTER", "LOGIN", "LEARN", "PAY"]),
            first_seen_at=first_seen,
            last_seen_at=first_seen + timedelta(days=random.randint(1, 90)),
        ))

    account_changes = []
    for i, inst in enumerate(institutions, 1):
        account_changes.append(EduInstitutionAccountChange(
            change_id=_id("EACC", batch, i),
            institution_id=inst.institution_id,
            old_account_hash=None if i == 1 else _hash(f"old-account-{batch}-{i}"),
            new_account_hash=_hash(f"new-account-{batch}-{i}"),
            account_type="PRIVATE" if inst.whitelist_status != "WHITE" else "SUPERVISION",
            change_reason=random.choice(["监管账户备案", "银行账户变更", "线下收款迁移"]),
            changed_at=_pick_time(120),
        ))

    return {
        "institutions": institutions,
        "users": users,
        "teachers": teachers,
        "courses": courses,
        "enrollments": enrollments,
        "contracts": contracts,
        "payments": payments,
        "lessons": lessons,
        "progress": progress_rows,
        "refunds": refunds,
        "complaints": complaints,
        "certs": certs,
        "rewards": rewards,
        "bindings": bindings,
        "account_changes": account_changes,
    }


async def insert_dataset(dataset: dict[str, list]) -> None:
    if AsyncSessionLocal is None:
        raise RuntimeError(f"当前 Python 环境缺少数据库依赖: {DB_IMPORT_ERROR}")
    # 这些 ORM 只做轻量表映射, 没有配置 relationship。
    # 因此必须按外键依赖顺序逐批 flush, 避免 SQLAlchemy 在 commit 时重排插入顺序。
    insert_order = [
        "institutions",
        "users",
        "teachers",
        "courses",
        "enrollments",
        "contracts",
        "payments",
        "lessons",
        "progress",
        "refunds",
        "complaints",
        "certs",
        "rewards",
        "bindings",
        "account_changes",
    ]
    async with AsyncSessionLocal() as db:
        try:
            for key in insert_order:
                db.add_all(dataset[key])
                await db.flush()
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def auto_assess_dataset(dataset: dict[str, list]) -> dict | None:
    """DB 模式造数后自动补评新报名单。SQL 文件模式无法自动评估。"""
    if AsyncSessionLocal is None:
        return None
    from app.routers.education import auto_assess_new_enrollments

    async with AsyncSessionLocal() as db:
        return await auto_assess_new_enrollments(
            db,
            enrollment_ids=[row.enrollment_id for row in dataset.get("enrollments", [])],
            event_type_map=build_random_event_type_map(dataset.get("enrollments", [])),
        )


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def write_sql_file(dataset: dict[str, list], output_path: str, *, include_delete: bool = False) -> Path:
    """生成可直接导入 MySQL 的业务数据 SQL, 不依赖 SQLAlchemy。"""
    path = Path(output_path)
    if not path.is_absolute():
        base_dir = Path(__file__).resolve().parents[1]
        path = base_dir / path
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "-- ============================================",
        "-- 教育行业风控系统 - 业务测试数据",
        "-- 由 scripts/gen_education_business_data.py 生成",
        "-- ============================================",
        "",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
    ]

    if include_delete:
        for key in reversed(TABLE_COLUMNS.keys()):
            table, _ = TABLE_COLUMNS[key]
            lines.append(f"DELETE FROM `{table}`;")
        lines.append("")

    for key, (table, columns) in TABLE_COLUMNS.items():
        rows = dataset[key]
        if not rows:
            continue
        quoted_cols = ", ".join(f"`{col}`" for col in columns)
        lines.append(f"-- {table}: {len(rows)} rows")
        for row in rows:
            values = ", ".join(_sql_literal(getattr(row, col)) for col in columns)
            lines.append(f"INSERT INTO `{table}` ({quoted_cols}) VALUES ({values});")
        lines.append("")

    lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def main() -> None:
    parser = argparse.ArgumentParser(description="生成教育行业业务测试数据")
    parser.add_argument("--count", type=int, default=120, help="报名主数据条数, 默认 120")
    parser.add_argument("--clear", action="store_true", help="先清空 15 张教育业务表")
    parser.add_argument("--seed", type=int, default=42, help="随机种子, 默认 42")
    parser.add_argument(
        "--mode",
        choices=["auto", "db", "sql"],
        default="auto",
        help="输出模式: auto=有依赖则入库, 无依赖则生成 SQL; db=直连数据库; sql=只生成 SQL 文件",
    )
    parser.add_argument(
        "--out",
        default="sql/init_education_business_data.sql",
        help="SQL 输出文件路径, 默认 sql/init_education_business_data.sql",
    )
    parser.add_argument(
        "--no-auto-risk",
        action="store_true",
        help="DB 模式下只插入业务数据, 不自动生成风险评估",
    )
    args = parser.parse_args()

    if args.count < 100:
        print(f"[WARN] --count={args.count} 小于 100, 自动提升到 100")
        args.count = 100

    random.seed(args.seed)
    batch = datetime.now().strftime("%m%d%H%M%S")

    try:
        dataset = build_dataset(args.count, batch)
        use_db = args.mode == "db" or (args.mode == "auto" and DB_IMPORT_ERROR is None)

        if use_db:
            await ensure_tables()
            if args.clear:
                await clear_education_tables()
            await insert_dataset(dataset)
            auto_risk_stats = None if args.no_auto_risk else await auto_assess_dataset(dataset)
            output_note = "已写入数据库"
        else:
            sql_path = write_sql_file(dataset, args.out, include_delete=args.clear)
            auto_risk_stats = None
            output_note = f"已生成 SQL 文件: {sql_path}"
            if DB_IMPORT_ERROR is not None and args.mode == "auto":
                print(f"[WARN] 当前 Python 环境缺少 {DB_IMPORT_ERROR.name}, 自动切换为 SQL 文件模式")
            elif args.mode == "db":
                raise RuntimeError(f"--mode db 需要项目数据库依赖: {DB_IMPORT_ERROR}")

        total_rows = sum(len(v) for v in dataset.values())
        print("=" * 60)
        print("教育行业业务数据生成完成")
        print(f"批次: {batch}")
        print(output_note)
        print(f"报名主数据: {len(dataset['enrollments'])} 条")
        if auto_risk_stats is not None:
            print(
                "自动风险评估: "
                f"新增评估 {auto_risk_stats['created_assessments']} 条, "
                f"新增案件 {auto_risk_stats['created_cases']} 条, "
                f"跳过已评估 {auto_risk_stats['skipped']} 条"
            )
            event_type_counts = auto_risk_stats.get("event_type_counts") or {}
            if event_type_counts:
                event_summary = "、".join(
                    f"{event_type}:{count}" for event_type, count in event_type_counts.items()
                )
                print(f"事件类型分布: {event_summary}")
        print(f"业务总行数: {total_rows} 条")
        for key, rows in dataset.items():
            print(f"  {key:<16} {len(rows):>4} 条")
        if not use_db:
            print("\n导入数据库前先执行表结构:")
            print('  cmd /c "mysql -uroot -p ecs < sql\\init_education_business_tables.sql"')
            print("再导入业务数据:")
            print(f'  cmd /c "mysql -uroot -p ecs < {sql_path}"')
        print("=" * 60)
    finally:
        if async_engine is not None:
            await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
