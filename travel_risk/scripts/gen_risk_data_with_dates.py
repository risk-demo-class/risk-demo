"""
旅游风控系统 - 生成带日期范围的评估数据 (仪表盘趋势用)
================
用法:
  python scripts/gen_risk_data_with_dates.py                # 近 7 天, 每天 1-30 条
  python scripts/gen_risk_data_with_dates.py --per-day 15   # 每天固定 15 条
  python scripts/gen_risk_data_with_dates.py --days 30 --per-day 10 --clean
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, rebuild_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def _pick_booking(db, risk_only: bool = False) -> tuple | None:
    like = "RISK%" if risk_only else "%"
    r = await db.execute(text("""
        SELECT b.booking_id, b.user_id FROM booking_info b
        WHERE b.user_id LIKE :like
        ORDER BY RAND() LIMIT 1
    """), {"like": like})
    row = r.first()
    return (row[0], row[1]) if row else None


async def gen_dated_data(days: int = 7, per_day: int | None = None, clean: bool = False):
    random.seed(42)
    async with AsyncSessionLocal() as db:
        if clean:
            for table in ("risk_feature", "risk_assessment", "risk_case", "risk_event"):
                await db.execute(text(f"DELETE FROM {table}"))
            await db.commit()

        total = 0
        for offset in range(days):
            day_count = per_day if per_day else random.randint(1, 30)
            day = datetime.now() - timedelta(days=offset)
            for _ in range(day_count):
                # 2/3 概率普通订单, 1/3 概率高风险用户 (保证趋势图有拒绝样本)
                risk_only = random.random() < 0.3
                row = await _pick_booking(db, risk_only=risk_only)
                if not row:
                    continue
                booking_id, user_id = row
                try:
                    resp = await process_event(db, RiskCheckRequest(
                        event_type="下单",
                        source_id=booking_id,
                        user_id=user_id,
                        event_data={"booking_id": booking_id},
                    ))
                    # 回填 create_time 到目标日期 (事件/评估/案件同步)
                    ts = day.replace(hour=random.randint(8, 22), minute=random.randint(0, 59), second=0)
                    await db.execute(text(
                        "UPDATE risk_event SET create_time=:ts WHERE event_id=:eid"
                    ), {"ts": ts, "eid": resp.event_id})
                    await db.execute(text(
                        "UPDATE risk_assessment SET create_time=:ts WHERE assessment_id=:aid"
                    ), {"ts": ts, "aid": resp.assessment_id})
                    await db.execute(text(
                        "UPDATE risk_case SET create_time=:ts, update_time=:ts WHERE assessment_id=:aid"
                    ), {"ts": ts, "aid": resp.assessment_id})
                    await db.commit()
                    total += 1
                except Exception as e:
                    await db.rollback()
            print(f"  day-{offset} ({day.date()}): {day_count} 条")

        print("\n" + "=" * 60)
        print(f"完成! 共生成 {total} 条带日期的评估")
        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成带日期的评估数据")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-day", type=int, default=None)
    parser.add_argument("--clean", action="store_true", help="先清空再生成")
    args = parser.parse_args()
    rebuild_engine()
    asyncio.run(gen_dated_data(args.days, args.per_day, args.clean))
