#!/usr/bin/env python3
"""生成 25 个教育行业高风险种子用户及其业务行为。"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models_business import (  # noqa: E402
    BlacklistExtra, Course, EducationCredential, LearningProgress, LiveReward,
    OrderInfo, RefundRequest, UserDevice, UserInfo,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> None:
    now = datetime.now()
    with SessionLocal.begin() as db:
        if db.get(UserInfo, "RISK-STU-001"):
            count = db.query(UserInfo).filter(UserInfo.user_id.like("RISK-STU-%")).count()
            print(f"gen_risky_users SKIP: 已存在 {count} 个风险种子用户")
            return

        teachers = [
            UserInfo(user_id=f"TEACHER-{i:02d}", name=f"教师{i}", role="老师", real_name_status="已认证", register_at=now - timedelta(days=800))
            for i in range(1, 3)
        ]
        db.add_all(teachers)
        db.flush()
        courses = [
            Course(course_id=f"COURSE-{i:02d}", name=f"教育风控课程{i}", category="职业教育", price=Decimal("6999.00"), teacher_id=teachers[(i - 1) % 2].user_id, total_hours=Decimal("40.00"), course_status="已上架")
            for i in range(1, 6)
        ]
        db.add_all(courses)
        db.flush()

        users = []
        for i in range(1, 26):
            users.append(UserInfo(
                user_id=f"RISK-STU-{i:03d}", name=f"风险学员{i:03d}", role="学生",
                student_id=f"RISK-SID-{i:03d}", real_name_status="已认证" if i % 4 else "认证失败",
                register_at=now - timedelta(days=(i % 6) + 1),
            ))
        db.add_all(users)
        db.flush()

        for i, user in enumerate(users, 1):
            # 每 5 人共享设备；第一组直接满足 R008。
            fp = digest(f"shared-device-{(i - 1) // 5}")
            db.add(UserDevice(user_id=user.user_id, device_fingerprint=fp, first_seen_at=now - timedelta(days=5), last_seen_at=now))
            course = courses[(i - 1) % len(courses)]
            order = OrderInfo(
                order_id=f"RISK-ORD-{i:03d}", user_id=user.user_id,
                learner_user_id=user.user_id, course_id=course.course_id,
                total_amount=Decimal("6999.00"), payment_account_hash=digest(f"shared-pay-{(i - 1) // 5}"),
                order_status="已支付", paid_at=now - timedelta(minutes=i),
                expected_finish_days=30,
            )
            db.add(order)
            db.flush()
            db.add(LearningProgress(
                user_id=user.user_id, course_id=course.course_id,
                total_minutes=2 if i <= 10 else 60, completion_rate=Decimal("0.50") if i <= 10 else Decimal("10.00"),
                last_active_at=now - timedelta(days=1),
            ))
            if i <= 10:
                db.add(RefundRequest(
                    refund_id=f"RISK-RF-{i:03d}", order_id=order.order_id,
                    requested_by_user_id=user.user_id, reason="几乎未学习即退费",
                    study_minutes_before_refund=2, requested_amount=Decimal("6999.00"),
                    refund_amount=None, refund_status="待审核", requested_at=now,
                ))
            if 11 <= i <= 15:
                db.add(LiveReward(
                    reward_id=f"RISK-RW-{i:03d}", live_session_id="LIVE-RISK-01",
                    user_id=user.user_id, reward_account_id=f"LIVE-ACCOUNT-{i:03d}",
                    transaction_type="打赏", amount=Decimal("6000.00"), reward_status="成功", rewarded_at=now,
                ))
            if 16 <= i <= 20:
                db.add(EducationCredential(
                    credential_id=f"RISK-CRED-{i:03d}", user_id=user.user_id,
                    id_card_ciphertext=f"cipher-{i}".encode(), id_card_hash=digest(f"id-card-{i}"),
                    id_card_masked=f"310***********{i:04d}"[-18:],
                    submitted_education_level="硕士", authoritative_education_level="高中",
                    verify_status="不匹配", mismatch_reason="学历层级不一致",
                    verify_source="demo-authority", submitted_at=now, verified_at=now,
                ))
            if i >= 21:
                db.add(BlacklistExtra(
                    type="学号", value=user.student_id, value_masked=user.student_id,
                    reason="高风险演示种子", status="启用", created_by="generator",
                ))
    print("gen_risky_users OK: high_risk_seed_users=25")


if __name__ == "__main__":
    main()
