"""
旅游行业风控系统 - 模拟风控评估数据生成

从旅游业务表中选择正常/风险两类样本，调用 process_event 生成:
risk_event / risk_feature / risk_assessment / risk_case / risk_user_profile。
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event


NORMAL_PICKERS = {
    "旅游下单": """
        SELECT o.order_id AS source_id, o.user_id, o.order_id
        FROM order_info o
        JOIN user_info u ON o.user_id = u.user_id
        LEFT JOIN destination_risk d ON o.dest_country = d.country AND o.dest_city = d.city
        WHERE o.risk_label = 0 AND u.risk_label = 0
          AND o.total_amount < 10000
          AND u.account_age_days >= 30
          AND COALESCE(d.risk_score, 0) < 60
        ORDER BY RAND() LIMIT 1
    """,
    "支付": """
        SELECT o.order_id AS source_id, o.user_id, o.order_id
        FROM order_info o
        JOIN user_info u ON o.user_id = u.user_id
        LEFT JOIN destination_risk d ON o.dest_country = d.country AND o.dest_city = d.city
        WHERE o.risk_label = 0 AND u.risk_label = 0
          AND o.payment_time IS NOT NULL
          AND o.total_amount < 10000
          AND u.account_age_days >= 30
          AND COALESCE(d.risk_score, 0) < 60
        ORDER BY RAND() LIMIT 1
    """,
    "酒店预订": """
        SELECT h.booking_id AS source_id, o.user_id, h.order_id
        FROM booking_hotel h
        JOIN order_info o ON h.order_id = o.order_id
        JOIN user_info u ON o.user_id = u.user_id
        LEFT JOIN destination_risk d ON o.dest_country = d.country AND o.dest_city = d.city
        WHERE o.risk_label = 0 AND u.risk_label = 0
          AND o.total_amount < 10000
          AND h.guest_document_status = '有效'
          AND COALESCE(d.risk_score, 0) < 60
        ORDER BY RAND() LIMIT 1
    """,
}


RISK_PICKERS = {
    "旅游下单": """
        SELECT o.order_id AS source_id, o.user_id, o.order_id
        FROM order_info o
        JOIN user_info u ON o.user_id = u.user_id
        LEFT JOIN destination_risk d ON o.dest_country = d.country AND o.dest_city = d.city
        WHERE o.risk_label = 1 OR u.risk_label = 1 OR o.total_amount >= 30000 OR COALESCE(d.risk_score, 0) >= 75
        ORDER BY RAND() LIMIT 1
    """,
    "机票预订": """
        SELECT f.booking_id AS source_id, o.user_id, f.order_id
        FROM booking_flight f
        JOIN order_info o ON f.order_id = o.order_id
        WHERE f.risk_label = 1 OR o.risk_label = 1 OR f.ticket_count >= 5 OR o.total_amount >= 15000
        ORDER BY RAND() LIMIT 1
    """,
    "酒店预订": """
        SELECT h.booking_id AS source_id, o.user_id, h.order_id
        FROM booking_hotel h
        JOIN order_info o ON h.order_id = o.order_id
        WHERE h.risk_label = 1 OR o.risk_label = 1 OR h.guest_document_status <> '有效' OR o.total_amount >= 15000
        ORDER BY RAND() LIMIT 1
    """,
    "签证申请": """
        SELECT visa_id AS source_id, user_id, order_id
        FROM visa_application
        WHERE risk_label = 1 OR reject_history >= 2 OR material_change_count >= 3 OR visa_status = '拒签'
        ORDER BY RAND() LIMIT 1
    """,
    "售后申请": """
        SELECT refund_id AS source_id, user_id, order_id
        FROM travel_refund
        WHERE risk_label = 1 OR refund_amount >= 8000
        ORDER BY RAND() LIMIT 1
    """,
    "投诉": """
        SELECT complaint_id AS source_id, user_id, order_id
        FROM travel_complaint
        WHERE risk_label = 1 OR compensation_amount >= 2000 OR complaint_type = '重复索赔'
        ORDER BY RAND() LIMIT 1
    """,
}


FALLBACK_PICKERS = {
    "旅游下单": "SELECT order_id AS source_id, user_id, order_id FROM order_info ORDER BY RAND() LIMIT 1",
    "支付": "SELECT order_id AS source_id, user_id, order_id FROM order_info WHERE payment_time IS NOT NULL ORDER BY RAND() LIMIT 1",
    "机票预订": """
        SELECT f.booking_id AS source_id, o.user_id, f.order_id
        FROM booking_flight f JOIN order_info o ON f.order_id = o.order_id
        ORDER BY RAND() LIMIT 1
    """,
    "酒店预订": """
        SELECT h.booking_id AS source_id, o.user_id, h.order_id
        FROM booking_hotel h JOIN order_info o ON h.order_id = o.order_id
        ORDER BY RAND() LIMIT 1
    """,
    "签证申请": "SELECT visa_id AS source_id, user_id, order_id FROM visa_application ORDER BY RAND() LIMIT 1",
    "售后申请": "SELECT refund_id AS source_id, user_id, order_id FROM travel_refund ORDER BY RAND() LIMIT 1",
    "投诉": "SELECT complaint_id AS source_id, user_id, order_id FROM travel_complaint ORDER BY RAND() LIMIT 1",
    "出行前核验": "SELECT order_id AS source_id, user_id, order_id FROM order_info ORDER BY RAND() LIMIT 1",
}


async def _reset_risk_data(db):
    await db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in (
        "risk_action_log",
        "risk_case",
        "risk_assessment",
        "risk_feature",
        "risk_event",
        "risk_user_profile",
        "risk_alert",
    ):
        await db.execute(text(f"TRUNCATE TABLE {table}"))
    await db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    await db.commit()


async def _pick_event(db, sample_type: str):
    picker_map = NORMAL_PICKERS if sample_type == "normal" else RISK_PICKERS
    event_type = random.choice(list(picker_map.keys()))
    row = (await db.execute(text(picker_map[event_type]))).first()
    if not row:
        fallback_event = random.choice(list(FALLBACK_PICKERS.keys()))
        row = (await db.execute(text(FALLBACK_PICKERS[fallback_event]))).first()
        event_type = fallback_event
    if not row:
        return None
    return event_type, row.source_id, row.user_id, row.order_id


async def generate_risk_data(count: int = 100, mode: str = "mixed", reset_risk_data: bool = False):
    success = 0
    persisted = 0
    pos_count = 0
    neg_count = 0
    async with AsyncSessionLocal() as db:
        if reset_risk_data:
            print("[RESET] 清空 risk_event/risk_feature/risk_assessment/risk_case/risk_user_profile")
            await _reset_risk_data(db)

        for i in range(count):
            if mode == "normal":
                sample_type = "normal"
            elif mode == "risk":
                sample_type = "risk"
            else:
                sample_type = "risk" if i % 2 == 0 else "normal"

            picked = await _pick_event(db, sample_type)
            if not picked:
                print(f"  [{i + 1}/{count}] 无可用业务数据, 跳过")
                continue

            event_type, source_id, user_id, order_id = picked
            request = RiskCheckRequest(
                event_type=event_type,
                source_id=source_id,
                user_id=user_id,
                order_id=order_id,
                event_data={
                    "_skip_blacklist": True,
                    "sample_type": sample_type,
                    "generated_by": "scripts/gen_risk_data.py",
                },
            )
            try:
                result = await process_event(db, request)
                success += 1
                if result.assessment_id == "blacklist_reject":
                    print(
                        f"  [{i + 1}/{count}] {sample_type:<6} {event_type:<6} user={user_id} source={source_id} "
                        f"blacklist_reject skipped"
                    )
                    continue

                persisted += 1
                is_pos = result.decision in ("人工审核", "拒绝")
                if is_pos:
                    pos_count += 1
                else:
                    neg_count += 1
                print(
                    f"  [{i + 1}/{count}] {sample_type:<6} {event_type:<6} user={user_id} source={source_id} "
                    f"score={result.final_score} decision={result.decision} rules={result.rule_count}"
                )
            except Exception as e:
                print(f"  [{i + 1}/{count}] {sample_type} 失败: {e}")

    pos_ratio = pos_count / persisted * 100 if persisted else 0
    neg_ratio = neg_count / persisted * 100 if persisted else 0
    print(
        f"\n完成: 调用成功 {success} 条, 落库评估 {persisted} 条, "
        f"正例 {pos_count} 条 ({pos_ratio:.1f}%), 负例 {neg_count} 条 ({neg_ratio:.1f}%)"
    )
    if persisted < 50:
        raise RuntimeError(f"落库评估只有 {persisted} 条，训练样本不足。请增大 --count 或检查规则/数据库。")
    if persisted and (pos_count == 0 or neg_count == 0):
        print("警告: 当前只有一个类别，无法训练二分类模型。建议使用 --mode mixed 并增加 --count。")
        raise RuntimeError("训练数据只有一个类别，无法训练二分类模型。")


async def _runner(args):
    from app.database import async_engine
    try:
        await generate_risk_data(args.count, args.mode, args.reset_risk_data)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成旅游风控评估数据")
    parser.add_argument("--count", type=int, default=100, help="生成评估条数")
    parser.add_argument("--mode", choices=["mixed", "normal", "risk"], default="mixed", help="样本模式")
    parser.add_argument("--reset-risk-data", action="store_true", help="先清空旧风控评估/特征/案件/画像数据")
    args = parser.parse_args()
    asyncio.run(_runner(args))
