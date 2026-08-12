"""
教育风控系统 - 风控评估数据生成器
批量运行业务数据通过风控引擎, 生成评估记录/案件/画像数据
用法: python scripts/gen_edu_risk_data.py [--count 10000]
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event
from app.models import OrderInfo


async def generate_risk_data(count: int = 10000):
    print("=" * 60)
    print(f"Education Risk Data Generator - {count} assessments")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        orders_result = await db.execute(
            select(OrderInfo.order_id, OrderInfo.user_id, OrderInfo.course_id)
            .order_by(OrderInfo.create_time.desc())
            .limit(5000)
        )
        orders = orders_result.all()
        print(f"Orders available: {len(orders)}")
        if len(orders) == 0:
            print("ERROR: No orders. Run gen_edu_data.py first.")
            return

    # ---- Phase 1: Pre-create refund & donation records ----
    print("\nPhase 1: Creating supporting records...")
    refund_ids = []
    donation_ids = []

    async with AsyncSessionLocal() as db:
        for i in range(count):
            order = orders[i % len(orders)]
            # Pre-create refund records for ~30% of assessments
            if random.random() < 0.30:
                rid = f"RFG{datetime.now().strftime('%m%d%H%M')}{i:06d}"
                try:
                    await db.execute(
                        text("INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, "
                             "study_minutes_before_refund, refund_amount, refund_status, create_time) "
                             "VALUES (:rid, :oid, :uid, '系统生成测试', :mins, :amt, '待审核', NOW())"),
                        {"rid": rid, "oid": order.order_id, "uid": order.user_id,
                         "mins": random.randint(0, 30),
                         "amt": round(random.uniform(50, 5000), 2)},
                    )
                    refund_ids.append((rid, order.order_id, order.user_id))
                except Exception:
                    pass

            # Pre-create donation records for ~20% of assessments
            if random.random() < 0.20:
                did = f"DNG{datetime.now().strftime('%m%d%H%M')}{i:06d}"
                try:
                    await db.execute(
                        text("INSERT IGNORE INTO donation_record (donation_id, user_id, course_id, amount, create_time) "
                             "VALUES (:did, :uid, :cid, :amt, NOW())"),
                        {"did": did, "uid": order.user_id,
                         "cid": order.course_id or "C001",
                         "amt": round(random.uniform(10, 8000), 2)},
                    )
                    donation_ids.append((did, order.user_id))
                except Exception:
                    pass

            if (i + 1) % 2000 == 0:
                await db.commit()
                print(f"  Created {len(refund_ids)} refunds + {len(donation_ids)} donations...")

        await db.commit()
        print(f"  Done: {len(refund_ids)} refunds + {len(donation_ids)} donations")

    # ---- Phase 2: Run risk checks in batches ----
    print(f"\nPhase 2: Running {count} risk assessments (batch size=100)...")
    stats = {"通过": 0, "标记": 0, "人工审核": 0, "拒绝": 0, "error": 0}

    refund_idx = 0
    donation_idx = 0
    BATCH = 100
    processed = 0

    for batch_start in range(0, count, BATCH):
        batch_end = min(batch_start + BATCH, count)
        async with AsyncSessionLocal() as db:
            for i in range(batch_start, batch_end):
                order = orders[i % len(orders)]
                r = random.random()

                if r < 0.50:
                    event_type = "报名"
                    source_id = order.order_id
                    order_id_val = order.order_id
                elif r < 0.80:
                    event_type = "退费申请"
                    if refund_idx < len(refund_ids):
                        source_id = refund_ids[refund_idx][0]
                        order_id_val = refund_ids[refund_idx][1]
                        refund_idx += 1
                    else:
                        continue
                else:
                    event_type = "打赏"
                    if donation_idx < len(donation_ids):
                        source_id = donation_ids[donation_idx][0]
                        order_id_val = None
                        donation_idx += 1
                    else:
                        continue

                try:
                    request = RiskCheckRequest(
                        event_type=event_type,
                        source_id=source_id,
                        user_id=order.user_id,
                        order_id=order_id_val,
                    )
                    result = await process_event(db, request)
                    stats[result.decision] = stats.get(result.decision, 0) + 1
                except Exception as e:
                    stats["error"] += 1
                    if stats["error"] <= 3:
                        print(f"  Err: {type(e).__name__}: {str(e)[:80]}")
                    await db.rollback()

                processed += 1

        if batch_end % 1000 == 0 or batch_end >= count:
            total = sum(stats.values())
            p_pass = stats["通过"] / total * 100 if total > 0 else 0
            p_rej = stats["拒绝"] / total * 100 if total > 0 else 0
            print(f"  [{batch_end}/{count}] pass={p_pass:.1f}% reject={p_rej:.1f}% "
                  f"review={stats['人工审核']} mark={stats['标记']} err={stats['error']}")

    total = sum(stats.values())
    print(f"\n{'='*60}")
    print(f"Complete! {total} assessments:")
    for k in sorted(stats, key=lambda x: stats.get(x, 0), reverse=True):
        v = stats.get(k, 0)
        print(f"  {k}: {v} ({v/total*100:.1f}%)" if total > 0 else f"  {k}: {v}")
    print(f"{'='*60}")


async def add_blacklist_entries():
    """Add 10 diverse blacklist entries."""
    entries = [
        ("学号", "STU20240100", "批量刷课作弊", None),
        ("学号", "STU20240101", "虚假身份注册-1年", 8760),
        ("学号", "STU20240102", "恶意退费惯犯-6个月", 4380),
        ("身份证号", "330102200501010001", "身份盗用", None),
        ("身份证号", "330102200502020002", "虚假认证-1年", 8760),
        ("身份证号", "330102200503030003", "涉诈关联", None),
        ("用户", "BLK_U0001", "多平台欺诈-3个月", 2160),
        ("用户", "BLK_U0002", "AI假学员", None),
        ("用户", "BLK_U0003", "支付争议-1个月", 720),
        ("设备指纹", "DEV_FRAUD_001", "关联多个欺诈账号", None),
    ]

    async with AsyncSessionLocal() as db:
        added = 0
        for bl_type, bl_value, reason, expire_hours in entries:
            from datetime import timedelta
            exp = (datetime.now() + timedelta(hours=expire_hours)).strftime("%Y-%m-%d %H:%M:%S") if expire_hours else None
            try:
                await db.execute(
                    text("INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) "
                         "VALUES (:t, :v, :r, :e)"),
                    {"t": bl_type, "v": bl_value, "r": reason, "e": exp},
                )
                await db.execute(
                    text("INSERT IGNORE INTO blacklist_extra (entry_id, type, value, reason, expire_at) "
                         "VALUES (:eid, :t, :v, :r, :exp)"),
                    {"eid": f"BL_G{added+1:03d}", "t": bl_type, "v": bl_value, "r": reason, "exp": exp},
                )
                added += 1
            except Exception as e:
                print(f"  Skip: {bl_type}={bl_value} ({e})")
        await db.commit()
        print(f"  Added {added}/10 blacklist entries")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--skip-blacklist", action="store_true")
    args = parser.parse_args()

    await generate_risk_data(args.count)

    if not args.skip_blacklist:
        print("\nAdding blacklist entries...")
        await add_blacklist_entries()

    await async_engine.dispose()
    print("\nDone! Run: python run_app.py")


if __name__ == "__main__":
    asyncio.run(main())
