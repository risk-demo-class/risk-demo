"""
旅游风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据, 让仪表盘趋势图有跨天数据

事件混合: 预订下单 / 退改申请 / 签证申请 (旅游版)
--balance-pos: 80% 概率从 RISK 高风险用户挑样本

用法:
    python scripts/gen_risk_data_with_dates.py                          # 近 7 天, 每天 1~30 条
    python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live   # 今日 50 条 (仪表盘可见)
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos
    python scripts/gen_risk_data_with_dates.py --clean
"""
import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402

RISKY_USER_PREFIX = "RISK"
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")


def _log_failure(target_time, request, error):
    os.makedirs(LOG_DIR, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "target_time": target_time.isoformat() if target_time else None,
        "user_id": getattr(request, "user_id", None),
        "event_type": getattr(request, "event_type", None),
        "source_id": getattr(request, "source_id", None),
        "error": str(error)[:500],
    }
    with open(FAIL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def clean_risk_tables(db):
    print("清空风控运行时表 (保留 risk_rule / risk_blacklist)...")
    for tbl in ["risk_feature", "risk_assessment", "risk_event", "risk_case", "risk_user_profile"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败: {e}")
    await db.commit()


async def _pick_order(db, balance_pos: bool) -> tuple | None:
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, user_id FROM order_info
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.user_id)
    r = await db.execute(text(
        "SELECT order_id, user_id FROM order_info ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_refund(db, balance_pos: bool) -> tuple | None:
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT refund_id, user_id FROM order_refund
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.refund_id, row.user_id)
    r = await db.execute(text(
        "SELECT refund_id, user_id FROM order_refund ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (row.refund_id, row.user_id) if row else None


async def _pick_visa(db, balance_pos: bool) -> tuple | None:
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT visa_id, user_id FROM visa_application
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.visa_id, row.user_id)
    r = await db.execute(text(
        "SELECT visa_id, user_id FROM visa_application ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (row.visa_id, row.user_id) if row else None


async def _make_request(db, balance_pos: bool) -> RiskCheckRequest | None:
    """按事件混合概率构造一个请求."""
    evt = random.choices(["预订下单", "退改申请", "签证申请"], weights=[60, 30, 10])[0]
    if evt == "预订下单":
        picked = await _pick_order(db, balance_pos)
        if not picked:
            return None
        order_id, user_id = picked
        return RiskCheckRequest(event_type="预订下单", source_id=order_id,
                                user_id=user_id, order_id=order_id)
    if evt == "退改申请":
        picked = await _pick_refund(db, balance_pos) or await _pick_order(db, balance_pos)
        if not picked:
            return None
        if picked[0].startswith("RFD_"):
            return RiskCheckRequest(event_type="退改申请", source_id=picked[0], user_id=picked[1])
        return RiskCheckRequest(event_type="预订下单", source_id=picked[0],
                                user_id=picked[1], order_id=picked[0])
    picked = await _pick_visa(db, balance_pos) or await _pick_order(db, balance_pos)
    if not picked:
        return None
    if picked[0].startswith("VISA_"):
        return RiskCheckRequest(event_type="签证申请", source_id=picked[0], user_id=picked[1])
    return RiskCheckRequest(event_type="预订下单", source_id=picked[0],
                            user_id=picked[1], order_id=picked[0])


async def generate_risk_data_with_dates(
    days: int = 7,
    per_day: int | None = None,
    max_per_day: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    clean: bool = False,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
    live: bool = False,
):
    """在指定日期范围内生成风控评估数据 (旅游版)."""
    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        end_dt = (datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                  if end_date else datetime.now())
        start_dt = (datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                    if start_date else (end_dt - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0))

        if target_pos_ratio is not None and not balance_pos:
            print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()} | "
              f"每天: {per_day if per_day is not None else f'随机1~{max_per_day}'} 条 | "
              f"live={live} balance_pos={balance_pos}")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_success = 0
        grand_positive = 0
        grand_fail = 0

        for day_offset in range(total_days):
            current_date = start_dt.date() + timedelta(days=day_offset)
            day_count = per_day if per_day is not None else random.randint(1, max_per_day)
            day_success = 0
            day_positive = 0
            for _ in range(day_count):
                target_time = current_date.strftime("%Y-%m-%d ") + \
                    f"{random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
                request = await _make_request(db, balance_pos)
                if request is None:
                    continue
                try:
                    result = await process_event(db, request)
                    if result.decision in ("拒绝", "人工审核"):
                        day_positive += 1
                    day_success += 1

                    # 回写时间 (live=False 时跨天回写, 趋势图有数据)
                    if not live:
                        ev_row = (await db.execute(text(
                            "SELECT event_id FROM risk_event WHERE user_id=:u ORDER BY create_time DESC LIMIT 1"
                        ), {"u": request.user_id})).first()
                        if ev_row:
                            await db.execute(text(
                                "UPDATE risk_event SET create_time=:t WHERE event_id=:eid"),
                                {"t": target_time, "eid": ev_row.event_id})
                            await db.execute(text(
                                "UPDATE risk_feature SET compute_time=:t WHERE event_id=:eid"),
                                {"t": target_time, "eid": ev_row.event_id})
                        ast_row = (await db.execute(text(
                            "SELECT assessment_id FROM risk_assessment WHERE user_id=:u ORDER BY create_time DESC LIMIT 1"
                        ), {"u": request.user_id})).first()
                        if ast_row:
                            await db.execute(text(
                                "UPDATE risk_assessment SET create_time=:t WHERE assessment_id=:aid"),
                                {"t": target_time, "aid": ast_row.assessment_id})
                            await db.execute(text(
                                "UPDATE risk_case SET create_time=:t WHERE assessment_id=:aid"),
                                {"t": target_time, "aid": ast_row.assessment_id})
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    grand_fail += 1
                    _log_failure(datetime.strptime(target_time, "%Y-%m-%d %H:%M:%S"), request, e)

            grand_positive += day_positive
            grand_success += day_success
            print(f"[{current_date}] 成功 {day_success}, 正例 {day_positive}")

        pos_ratio = grand_positive / grand_success * 100 if grand_success else 0
        print("=" * 50)
        print(f"完成! 成功 {grand_success}, 失败 {grand_fail}, 正例 {grand_positive} ({pos_ratio:.1f}%)")
        if grand_fail > 0:
            print(f"失败详情: {FAIL_LOG}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="旅游版带日期范围的造评估数据")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None)
    parser.add_argument("--max-per-day", type=int, default=30)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--balance-pos", action="store_true")
    parser.add_argument("--target-pos-ratio", type=float, default=None)
    args = parser.parse_args()

    async def _runner():
        from app.database import async_engine
        try:
            await generate_risk_data_with_dates(
                days=args.days, per_day=args.per_day, max_per_day=args.max_per_day,
                start_date=args.start, end_date=args.end, clean=args.clean,
                balance_pos=args.balance_pos, target_pos_ratio=args.target_pos_ratio,
                live=args.live,
            )
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())
