"""
旅游风控系统 - 从业务数据生成风控评估记录
================
从现有订单/支付/退改/理赔/投诉里随机挑记录, 走 process_event() 完整流水线,
生成 risk_event / risk_feature / risk_assessment / risk_case.

用法:
  python scripts/gen_risk_data.py                # 默认 30 条
  python scripts/gen_risk_data.py 100            # 100 条
  python scripts/gen_risk_data.py 200 --balance-pos   # 优先挑 RISK00X 高风险用户 (训练用)
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, rebuild_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def _fetch_ids(db, sql: str, params: dict | None = None) -> list[tuple]:
    result = await db.execute(text(sql), params or {})
    return [tuple(r) for r in result.fetchall()]


async def gen_risk_data(count: int = 30, balance_pos: bool = False):
    async with AsyncSessionLocal() as db:
        # 1. 订单 → 下单事件 (优先 RISK 用户)
        if balance_pos:
            booking_sql = """
                SELECT b.booking_id, b.user_id FROM booking_info b
                WHERE b.user_id LIKE 'RISK%'
                ORDER BY RAND() LIMIT :n
            """
        else:
            booking_sql = """
                SELECT b.booking_id, b.user_id FROM booking_info b
                ORDER BY RAND() LIMIT :n
            """
        bookings = await _fetch_ids(db, booking_sql, {"n": count})

        # 2. 支付 → 支付事件
        payments = await _fetch_ids(db, """
            SELECT p.payment_id, p.user_id FROM payment_info p
            ORDER BY RAND() LIMIT :n
        """, {"n": max(count // 2, 5)})

        # 3. 退改 → 退改申请事件
        refunds = await _fetch_ids(db, """
            SELECT r.refund_id, b.user_id FROM refund_change r
            JOIN booking_info b ON r.booking_id = b.booking_id
            ORDER BY RAND() LIMIT :n
        """, {"n": max(count // 2, 5)})

        # 4. 理赔 → 理赔申请事件
        claims = await _fetch_ids(db, """
            SELECT c.claim_id, c.user_id FROM claim_info c
            ORDER BY RAND() LIMIT :n
        """, {"n": max(count // 3, 3)})

        # 5. 投诉 → 投诉事件
        complaints = await _fetch_ids(db, """
            SELECT c.complaint_id, c.user_id FROM complaint_info c
            ORDER BY RAND() LIMIT :n
        """, {"n": max(count // 3, 3)})

        # 6. 注册 → 注册事件 (纯用户特征)
        users = await _fetch_ids(db, """
            SELECT u.user_id, u.user_id FROM user_info u
            ORDER BY RAND() LIMIT :n
        """, {"n": max(count // 3, 3)})

        print(f"订单 {len(bookings)} / 支付 {len(payments)} / 退改 {len(refunds)} / 理赔 {len(claims)} / 投诉 {len(complaints)} / 注册 {len(users)}")

        total = 0
        rejected = 0
        for booking_id, user_id in bookings:
            try:
                resp = await process_event(db, RiskCheckRequest(
                    event_type="下单",
                    source_id=booking_id,
                    user_id=user_id,
                    event_data={"booking_id": booking_id},
                ))
                total += 1
                if resp.decision == "拒绝":
                    rejected += 1
                if total % 10 == 0:
                    print(f"  已处理 {total} 条, 拒绝 {rejected} 条")
            except Exception as e:
                await db.rollback()
                print(f"  [跳过] {booking_id}: {type(e).__name__}: {str(e)[:80]}")

        for payment_id, user_id in payments:
            try:
                await process_event(db, RiskCheckRequest(
                    event_type="支付", source_id=payment_id, user_id=user_id,
                    event_data={"payment_id": payment_id},
                ))
                total += 1
            except Exception as e:
                await db.rollback()
                print(f"  [跳过] 支付 {payment_id}: {str(e)[:80]}")

        for refund_id, user_id in refunds:
            try:
                await process_event(db, RiskCheckRequest(
                    event_type="退改申请", source_id=refund_id, user_id=user_id,
                    event_data={"refund_id": refund_id},
                ))
                total += 1
            except Exception as e:
                await db.rollback()
                print(f"  [跳过] 退改 {refund_id}: {str(e)[:80]}")

        for claim_id, user_id in claims:
            try:
                await process_event(db, RiskCheckRequest(
                    event_type="理赔申请", source_id=claim_id, user_id=user_id,
                    event_data={"claim_id": claim_id},
                ))
                total += 1
            except Exception as e:
                await db.rollback()
                print(f"  [跳过] 理赔 {claim_id}: {str(e)[:80]}")

        for complaint_id, user_id in complaints:
            try:
                await process_event(db, RiskCheckRequest(
                    event_type="投诉", source_id=complaint_id, user_id=user_id,
                    event_data={"complaint_id": complaint_id},
                ))
                total += 1
            except Exception as e:
                await db.rollback()
                print(f"  [跳过] 投诉 {complaint_id}: {str(e)[:80]}")

        for user_id, _ in users:
            try:
                await process_event(db, RiskCheckRequest(
                    event_type="注册", source_id=user_id, user_id=user_id,
                    event_data={"register_channel": "APP"},
                ))
                total += 1
            except Exception as e:
                await db.rollback()
                print(f"  [跳过] 注册 {user_id}: {str(e)[:80]}")

        print("\n" + "=" * 60)
        print(f"完成! 共生成 {total} 条评估 (拒绝 {rejected} 条)")
        print("下一步: python scripts/train_xgb_model.py")
        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从业务数据生成风控评估")
    parser.add_argument("count", type=int, nargs="?", default=30, help="评估条数 (默认 30)")
    parser.add_argument("--balance-pos", action="store_true", help="优先挑 RISK 高风险用户 (训练用)")
    args = parser.parse_args()
    rebuild_engine()
    asyncio.run(gen_risk_data(args.count, args.balance_pos))
