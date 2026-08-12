"""可重复执行的演示数据：正常报名、共享设备风险、黑名单。"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import CredentialVerification, Course, DeviceBinding, Enrollment, RefundRequest, RiskBlacklist, RiskRule, Student


def _add_student_with_enrollment(
    session: Session,
    user_id: str,
    enrollment_id: str,
    device_hash: str,
    course_id: str,
) -> None:
    session.add(Student(user_id=user_id, name_masked="张*", student_id_hash=f"hash-{user_id}"))
    session.add(
        Enrollment(
            enrollment_id=enrollment_id,
            user_id=user_id,
            course_id=course_id,
            paid_amount=1999.0,
            discount_amount=0.0,
            enroll_at=datetime.now(),
            status="已报名",
        )
    )
    session.add(
        DeviceBinding(
            binding_id=f"DEV-{user_id}",
            user_id=user_id,
            device_fingerprint_hash=device_hash,
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        )
    )


def _seed_refund_demo(session: Session, course_id: str) -> None:
    if session.get(Student, "STU-REFUND-001") is None:
        _add_student_with_enrollment(
            session, "STU-REFUND-001", "ENR-REFUND-001", "device-refund-hash", course_id
        )
    if session.get(RefundRequest, "REF-RISK-001") is None:
        session.add(
            RefundRequest(
                refund_id="REF-RISK-001",
                enrollment_id="ENR-REFUND-001",
                reason="课程与预期不符",
                study_minutes_before_refund=2,
                refund_amount=1999.0,
                status="申请中",
                apply_at=datetime.now(),
            )
        )
    if session.get(RiskRule, "EDU-RULE-REFUND-001") is None:
        session.add(
            RiskRule(
                rule_id="EDU-RULE-REFUND-001",
                rule_name="学习不足五分钟即申请退款",
                event_type="退费申请",
                rule_condition=json.dumps(
                    {"field": "refund_study_minutes_before_refund", "op": "<=", "value": 5}
                ),
                risk_score=65,
                action="人工审核",
                is_enabled=True,
            )
        )


def _seed_verification_demo(session: Session) -> None:
    if session.get(Student, "STU-VERIFY-001") is None:
        session.add(
            Student(
                user_id="STU-VERIFY-001",
                name_masked="李*",
                student_id_hash="hash-STU-VERIFY-001",
            )
        )
    for index in range(1, 4):
        verification_id = f"VER-RISK-00{index}"
        if session.get(CredentialVerification, verification_id) is None:
            session.add(
                CredentialVerification(
                    verification_id=verification_id,
                    user_id="STU-VERIFY-001",
                    verification_type="学历认证",
                    id_card_hash="id-hash-verify-demo",
                    status="审核失败",
                    failure_reason="演示用材料校验失败",
                    submit_at=datetime.now(),
                )
            )
    if session.get(RiskRule, "EDU-RULE-VERIFY-001") is None:
        session.add(
            RiskRule(
                rule_id="EDU-RULE-VERIFY-001",
                rule_name="三十天内连续学历认证失败",
                event_type="学历认证",
                rule_condition=json.dumps(
                    {"field": "credential_failure_count_30d", "op": ">=", "value": 3}
                ),
                risk_score=65,
                action="人工审核",
                is_enabled=True,
            )
        )


def seed_demo_data() -> None:
    """仅在库为空时初始化演示数据，不覆盖已有业务数据。"""
    session = SessionLocal()
    try:
        course_id = "CRS-PY-001"
        if session.get(Student, "STU-NORMAL-001") is not None:
            _seed_refund_demo(session, course_id)
            _seed_verification_demo(session)
            session.commit()
            return

        session.add(
            Course(
                course_id=course_id,
                name="Python 数据分析实战",
                category="职业技能",
                price=1999.0,
                teacher_id="TCH-001",
                total_hours=36,
            )
        )
        _add_student_with_enrollment(
            session, "STU-NORMAL-001", "ENR-NORMAL-001", "device-normal-hash", course_id
        )
        for index in range(1, 6):
            _add_student_with_enrollment(
                session,
                f"STU-RISK-{index:02d}",
                f"ENR-RISK-{index:03d}",
                "device-shared-hash",
                course_id,
            )
        _add_student_with_enrollment(
            session, "STU-BLACK-001", "ENR-BLACK-001", "device-black-hash", course_id
        )
        session.add(
            RiskRule(
                rule_id="EDU-RULE-001",
                rule_name="七日内共享设备关联多个新报名账号",
                event_type="课程报名",
                rule_condition=json.dumps(
                    {"field": "device_linked_users_7d", "op": ">=", "value": 5}
                ),
                risk_score=65,
                action="人工审核",
                is_enabled=True,
            )
        )
        session.add(
            RiskBlacklist(
                blacklist_type="用户",
                blacklist_value="STU-BLACK-001",
                reason="演示用已确认作弊账号",
            )
        )
        _seed_refund_demo(session, course_id)
        _seed_verification_demo(session)
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed_demo_data()
    print("教育风控演示数据初始化完成")
