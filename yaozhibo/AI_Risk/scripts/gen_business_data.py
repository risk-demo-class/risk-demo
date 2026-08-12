"""
生成可重复的在线教育业务数据，并通过 ``process_event`` 跑完整风控流水线。

默认生成不少于 150 个业务事件，其中固定植入 A~F 六类可解释场景。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app.config import BusinessEventType
from app.database import AsyncSessionLocal
from app.models import (
    BlacklistExtra,
    Course,
    LearningProgress,
    OrderInfo,
    RefundRequest,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
    UserInfo,
)
from app.schemas import RiskCheckRequest
from app.service.event import process_event


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _clean_generated_data(db) -> None:
    event_ids = list((await db.execute(
        select(RiskEvent.event_id).where(RiskEvent.event_source_id.like("GEN-%"))
    )).scalars())
    if event_ids:
        assessment_ids = list((await db.execute(
            select(RiskAssessment.assessment_id).where(RiskAssessment.event_id.in_(event_ids))
        )).scalars())
        if assessment_ids:
            await db.execute(delete(RiskCase).where(RiskCase.assessment_id.in_(assessment_ids)))
        await db.execute(delete(RiskAssessment).where(RiskAssessment.event_id.in_(event_ids)))
        await db.execute(delete(RiskFeature).where(RiskFeature.event_id.in_(event_ids)))
        await db.execute(delete(RiskEvent).where(RiskEvent.event_id.in_(event_ids)))
    await db.execute(delete(RiskUserProfile).where(RiskUserProfile.user_id.like("GEN-%")))

    await db.execute(delete(RefundRequest).where(RefundRequest.refund_id.like("GEN-%")))
    await db.execute(delete(LearningProgress).where(LearningProgress.progress_id.like("GEN-%")))
    await db.execute(delete(OrderInfo).where(OrderInfo.order_id.like("GEN-%")))
    await db.execute(delete(BlacklistExtra).where(BlacklistExtra.reason.like("教学生成器%")))
    await db.execute(delete(Course).where(Course.course_id.like("GEN-%")))
    await db.execute(delete(UserInfo).where(UserInfo.user_id.like("GEN-%")))
    await db.commit()


def _build_data(event_count: int, seed: int):
    if event_count < 100:
        raise ValueError("--events 至少为 100")
    rng = random.Random(seed)
    now = datetime.now().replace(microsecond=0)
    # 风险族随总事件量扩展：D约5%、E约15%、B退费约5%，正例约25%。
    b_count = max(1, int(event_count * 0.05))
    d_count = max(6, int(event_count * 0.05))
    e_order_count = max(4, int(event_count * 0.15))

    teacher = UserInfo(
        user_id="GEN-TEACHER", name="教学老师", role="teacher",
        student_id=None, id_card_hash=_hash("GEN-TEACHER"), real_name_status="VERIFIED",
        register_at=now - timedelta(days=500), device_id="GEN-DEV-TEACHER",
    )
    users = [teacher]
    for i in range(1, 61):
        users.append(UserInfo(
            user_id=f"GEN-U{i:03d}", name=f"学员{i:03d}", role="student",
            student_id=f"GEN-STU-{i:03d}", id_card_hash=_hash(f"GEN-ID-{i:03d}"),
            real_name_status="VERIFIED",
            register_at=now - timedelta(days=rng.randint(30, 500)),
            device_id=f"GEN-DEV-{i:03d}",
        ))

    # B/C/D/E/F 风险用户；D1~D6 共用设备。
    risk_users = {
        "B": UserInfo(user_id="GEN-RISK-B", name="0学时退费B", role="student", student_id="GEN-STU-B", id_card_hash=_hash("GEN-ID-B"), real_name_status="VERIFIED", register_at=now - timedelta(days=20), device_id="GEN-DEV-B"),
        "C": UserInfo(user_id="GEN-RISK-C", name="连环退费C", role="student", student_id="GEN-STU-C", id_card_hash=_hash("GEN-ID-C"), real_name_status="VERIFIED", register_at=now - timedelta(days=300), device_id="GEN-DEV-C"),
        "E": UserInfo(user_id="GEN-RISK-E", name="大额连报E", role="student", student_id="GEN-STU-E", id_card_hash=_hash("GEN-ID-E"), real_name_status="VERIFIED", register_at=now - timedelta(days=2), device_id="GEN-DEV-E"),
        "F": UserInfo(user_id="GEN-RISK-F", name="黑学号F", role="student", student_id="GEN-STU-F", id_card_hash=_hash("GEN-ID-F"), real_name_status="VERIFIED", register_at=now - timedelta(days=100), device_id="GEN-DEV-F"),
    }
    users.extend(risk_users.values())
    for i in range(2, b_count + 1):
        users.append(UserInfo(
            user_id=f"GEN-RISK-B{i}", name=f"0学时退费B{i}", role="student",
            student_id=f"GEN-STU-B{i}", id_card_hash=_hash(f"GEN-ID-B{i}"),
            real_name_status="VERIFIED", register_at=now - timedelta(days=20),
            device_id=f"GEN-DEV-B{i}",
        ))
    for i in range(1, d_count + 1):
        users.append(UserInfo(
            user_id=f"GEN-RISK-D{i}", name=f"代理账号D{i}", role="student",
            student_id=f"GEN-STU-D{i}", id_card_hash=_hash(f"GEN-ID-D{i}"),
            real_name_status="VERIFIED", register_at=now - timedelta(days=2),
            device_id="GEN-DEV-SHARED-D",
        ))

    courses = [
        Course(course_id=f"GEN-C{i:02d}", name=f"教育风控课程{i}", category=["编程", "AI", "数学", "英语"][i % 4],
               price=Decimal(str([3999, 6999, 8999, 9999, 12000][i % 5])), teacher_id="GEN-TEACHER",
               total_hours=40 + i * 5, audience_role="student", status="ACTIVE", created_at=now - timedelta(days=100))
        for i in range(1, 9)
    ]

    normal_order_count = max(35, int(event_count * 0.35))
    orders: list[OrderInfo] = []
    for i in range(1, normal_order_count + 1):
        uid = f"GEN-U{((i - 1) % 60) + 1:03d}"
        course = courses[(i - 1) % len(courses)]
        orders.append(OrderInfo(
            order_id=f"GEN-ORD-{i:04d}", user_id=uid, course_id=course.course_id,
            order_type="PURCHASE", total_amount=course.price, payment_status="PAID",
            study_goal="正常学习", expected_finish_days=90,
            created_at=now - timedelta(days=rng.randint(1, 60), hours=rng.randint(2, 20)),
        ))

    # D: 同设备六账号，同课程集中报名；E: 1小时内超过 30000。
    for i in range(1, d_count + 1):
        orders.append(OrderInfo(order_id=f"GEN-ORD-D{i}", user_id=f"GEN-RISK-D{i}", course_id="GEN-C01", order_type="PURCHASE", total_amount=Decimal("6999"), payment_status="PAID", study_goal="集中报名", expected_finish_days=30, created_at=now - timedelta(minutes=(i % 50) + 1)))
    for i in range(1, e_order_count + 1):
        course_id = f"GEN-C{((i + 1) % 8) + 1:02d}"
        orders.append(OrderInfo(order_id=f"GEN-ORD-E{i}", user_id="GEN-RISK-E", course_id=course_id, order_type="PURCHASE", total_amount=Decimal("9000"), payment_status="PAID", study_goal="大额连报", expected_finish_days=20, created_at=now - timedelta(minutes=(i % 50) + 1)))
    for i in range(1, b_count + 1):
        suffix = "" if i == 1 else str(i)
        orders.append(OrderInfo(order_id=f"GEN-ORD-B{suffix}", user_id=f"GEN-RISK-B{suffix}", course_id="GEN-C02", order_type="PURCHASE", total_amount=Decimal("8999"), payment_status="PAID", study_goal="试学", expected_finish_days=30, created_at=now - timedelta(minutes=30 + i)))
    orders.append(OrderInfo(order_id="GEN-ORD-F", user_id="GEN-RISK-F", course_id="GEN-C01", order_type="PURCHASE", total_amount=Decimal("6999"), payment_status="PAID", study_goal="黑学号测试", expected_finish_days=30, created_at=now - timedelta(minutes=10)))

    # C 的四笔订单和退费均在90天内。
    for i in range(1, 5):
        orders.append(OrderInfo(order_id=f"GEN-ORD-C{i}", user_id="GEN-RISK-C", course_id=f"GEN-C{i:02d}", order_type="PURCHASE", total_amount=Decimal("6000"), payment_status="REFUNDED", study_goal="连环退费", expected_finish_days=30, created_at=now - timedelta(days=i * 10)))

    progress_count = max(b_count, int(event_count * 0.20))
    progresses: list[LearningProgress] = []
    seen_pairs = set()
    for i in range(1, b_count + 1):
        suffix = "" if i == 1 else str(i)
        progresses.append(LearningProgress(
            progress_id=f"GEN-PRG-B{suffix or '1'}", user_id=f"GEN-RISK-B{suffix}",
            course_id="GEN-C02", order_id=f"GEN-ORD-B{suffix}", total_minutes=1,
            completion_rate=Decimal("0.0003"), last_active_at=now - timedelta(minutes=10),
            created_at=now - timedelta(minutes=30 + i),
        ))
        seen_pairs.add((f"GEN-RISK-B{suffix}", "GEN-C02"))
    for order in orders:
        pair = (order.user_id, order.course_id)
        if pair in seen_pairs or len(progresses) >= progress_count:
            continue
        seen_pairs.add(pair)
        minutes = rng.randint(120, 2400)
        if order.order_id.startswith("GEN-ORD-B"):
            minutes = 1
        progresses.append(LearningProgress(
            progress_id=f"GEN-PRG-{len(progresses)+1:04d}", user_id=order.user_id,
            course_id=order.course_id, order_id=order.order_id, total_minutes=minutes,
            completion_rate=Decimal(str(round(min(minutes / 3600, 1), 4))),
            last_active_at=now - timedelta(hours=rng.randint(1, 72)), created_at=order.created_at,
        ))

    refunds: list[RefundRequest] = []
    for i in range(1, b_count + 1):
        suffix = "" if i == 1 else str(i)
        refunds.append(RefundRequest(
            refund_id=f"GEN-REF-B{suffix}", order_id=f"GEN-ORD-B{suffix}",
            user_id=f"GEN-RISK-B{suffix}", reason="学习1分钟立即退费",
            study_minutes_before_refund=1, refund_amount=Decimal("8999"), status="PENDING",
            created_at=now - timedelta(minutes=5 + i),
        ))
    for i in range(1, 5):
        refunds.append(RefundRequest(refund_id=f"GEN-REF-C{i}", order_id=f"GEN-ORD-C{i}", user_id="GEN-RISK-C", reason=f"连环退费{i}", study_minutes_before_refund=30 + i, refund_amount=Decimal("6000"), status="APPROVED" if i < 4 else "PENDING", created_at=now - timedelta(days=i * 10 - 1)))

    # 补齐退费事件数，正常退费学时均 > 5 分钟。
    target_refunds = max(15, event_count - len(orders) - len(progresses))
    for order in orders:
        if len(refunds) >= target_refunds:
            break
        if order.user_id.startswith("GEN-U"):
            refunds.append(RefundRequest(
                refund_id=f"GEN-REF-{len(refunds)+1:04d}", order_id=order.order_id,
                user_id=order.user_id, reason="正常课程调整", study_minutes_before_refund=120,
                refund_amount=Decimal(str(min(float(order.total_amount), 1000))), status="PENDING",
                created_at=now - timedelta(days=rng.randint(1, 30)),
            ))

    blacklists = [BlacklistExtra(type="student_id", value="GEN-STU-F", reason="教学生成器：历史欺诈学号", status="ACTIVE", expire_at=None, created_at=now)]
    return users, courses, orders, progresses, refunds, blacklists


async def generate_business_data(event_count: int, seed: int, run_risk: bool = True) -> dict:
    users, courses, orders, progresses, refunds, blacklists = _build_data(event_count, seed)
    async with AsyncSessionLocal() as db:
        await _clean_generated_data(db)
        db.add_all(users)
        await db.flush()
        db.add_all(courses)
        await db.flush()
        db.add_all(orders)
        await db.flush()
        db.add_all(progresses)
        db.add_all(refunds)
        db.add_all(blacklists)
        await db.commit()

    requests = []
    for item in orders:
        requests.append(RiskCheckRequest(event_type=BusinessEventType.COURSE_PURCHASE, source_id=item.order_id, user_id=item.user_id, event_data={"course_id": item.course_id}))
    for item in progresses:
        requests.append(RiskCheckRequest(event_type=BusinessEventType.LEARNING_ACTIVITY, source_id=item.progress_id, user_id=item.user_id, event_data={"course_id": item.course_id}))
    for item in refunds:
        requests.append(RiskCheckRequest(event_type=BusinessEventType.REFUND_REQUEST, source_id=item.refund_id, user_id=item.user_id, event_data={"order_id": item.order_id}))

    decisions: dict[str, int] = {}
    rule_hits: dict[str, int] = {}
    if run_risk:
        for index, request in enumerate(requests, 1):
            async with AsyncSessionLocal() as db:
                result = await process_event(db, request)
            decisions[result.decision] = decisions.get(result.decision, 0) + 1
            for hit in result.triggered_rules:
                rule_hits[hit.rule_id] = rule_hits.get(hit.rule_id, 0) + 1
            if index % 25 == 0:
                print(f"  已完成风控评估 {index}/{len(requests)}")

    return {
        "users": len(users), "courses": len(courses), "orders": len(orders),
        "learning_progress": len(progresses), "refunds": len(refunds),
        "business_events": len(requests), "decisions": decisions, "rule_hits": rule_hits,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="生成在线教育业务数据并跑风控流水线")
    parser.add_argument("--events", type=int, default=150, help="业务事件总数，至少100")
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--skip-risk", action="store_true", help="只生成业务数据，不跑process_event")
    args = parser.parse_args()
    result = await generate_business_data(args.events, args.seed, run_risk=not args.skip_risk)
    print("教育业务数据生成完成")
    for key, value in result.items():
        print(f"  {key:<22} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
