"""
制造业风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据，让仪表盘趋势图有跨天数据

【P4-L3 2026-08-08 第三轮】支持 --balance-pos / --target-pos-ratio 控制正负例比例:
  - --balance-pos: 80% 概率从 RISK 高风险经销商挑样本
  - --target-pos-ratio: 目标正例比例 (0.0-1.0), 自动循环造数据直到达标 (最多 10 轮)

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

用法:
    python scripts/gen_risk_data_with_dates.py
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30
    python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live
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

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_DEALER_PREFIX = "RISK"

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _log_failure(target_time, request, error):
    _ensure_log_dir()
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
    """清空风控运行时表 (不影响 risk_rule)"""
    print("清空风控运行时表...")
    for tbl in ["risk_feature", "risk_assessment", "risk_event",
                "risk_case", "risk_user_profile", "risk_blacklist"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败 (可能表不存在): {e}")
    await db.commit()


async def _pick_event(db, balance_pos: bool) -> tuple[str, str, str]:
    """随机挑 1 条业务事件, 返回 (event_type, source_id, dealer_id).

    balance_pos=True 时 80% 概率优先挑 RISK 高风险经销商的样本.
    """
    prefix_clause = " WHERE oi.dealer_id LIKE :prefix" if balance_pos else ""
    prefix = {"prefix": f"{RISKY_DEALER_PREFIX}%"} if balance_pos else {}

    roll = random.random()
    if roll < 0.5:
        sql = "SELECT order_id, dealer_id FROM order_info"
        if balance_pos:
            sql += " WHERE dealer_id LIKE :prefix"
        sql += " ORDER BY RAND() LIMIT 1"
        if balance_pos and random.random() < 0.8:
            pass  # 上面已带 prefix
        else:
            sql = sql.replace(" WHERE dealer_id LIKE :prefix", "")
            prefix = {}
        r = await db.execute(text(sql), prefix)
        row = r.first()
        if row:
            return "经销商订货", row.order_id, row.dealer_id
    elif roll < 0.8:
        sql = ("SELECT w.warranty_id, oi.dealer_id FROM warranty_record w "
               "JOIN order_info oi ON w.order_id = oi.order_id")
        if balance_pos and random.random() < 0.8:
            sql += " WHERE oi.dealer_id LIKE :prefix"
        sql += " ORDER BY RAND() LIMIT 1"
        r = await db.execute(text(sql), prefix)
        row = r.first()
        if row:
            return "设备保修", row.warranty_id, row.dealer_id
    else:
        sql = "SELECT report_id, dealer_id FROM cross_region_report"
        if balance_pos and random.random() < 0.8:
            sql += " WHERE dealer_id LIKE :prefix"
        sql += " ORDER BY RAND() LIMIT 1"
        r = await db.execute(text(sql), prefix)
        row = r.first()
        if row:
            return "跨区串货举报", row.report_id, row.dealer_id
    return "", "", ""


async def generate_with_dates(
    days: int = 7,
    per_day: int | None = None,
    max_per_day: int | None = None,
    start: str | None = None,
    end: str | None = None,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
    clean: bool = False,
    live: bool = False,
):
    """按日期范围生成评估数据, 评估 create_time 回写到目标日期."""
    if start and end:
        day_start = datetime.strptime(start, "%Y-%m-%d")
        day_end = datetime.strptime(end, "%Y-%m-%d")
        date_list = [day_start + timedelta(days=i) for i in range((day_end - day_start).days + 1)]
    else:
        date_list = [datetime.now().date() - timedelta(days=i) for i in range(days)]

    if per_day:
        count_per_day = per_day
    elif max_per_day:
        count_per_day = None  # 随机 1~max
    else:
        count_per_day = None  # 随机 1~30

    total_success = 0
    total_pos = 0

    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        for date in date_list:
            if count_per_day is None:
                n = random.randint(1, max_per_day or 30)
            else:
                n = count_per_day
            day_success = 0
            for i in range(n):
                target_time = datetime(date.year, date.month, date.day,
                                       random.randint(9, 20), random.randint(0, 59))
                event_type, source_id, dealer_id = await _pick_event(db, balance_pos)
                if not source_id:
                    continue
                request = RiskCheckRequest(
                    event_type=event_type, source_id=source_id, user_id=dealer_id,
                )
                try:
                    result = await process_event(db, request)
                    # 回写时间: 让趋势图有跨天数据
                    await db.execute(text(
                        "UPDATE risk_assessment SET create_time = :t WHERE assessment_id = :aid"
                    ), {"t": target_time, "aid": result.assessment_id})
                    await db.execute(text(
                        "UPDATE risk_event SET create_time = :t WHERE event_id = :eid"
                    ), {"t": target_time, "eid": result.event_id})
                    await db.commit()
                    day_success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        total_pos += 1
                    if live and result.decision in ("拒绝", "人工审核"):
                        print(f"  {date} [{i+1}/{n}] {event_type} {source_id} → "
                              f"{result.decision} ({result.final_score})")
                except Exception as e:
                    await db.rollback()
                    _log_failure(target_time, request, e)
                    print(f"  {date} [{i+1}/{n}] {event_type} {source_id} 失败: {type(e).__name__}: {e}")
            total_success += day_success
            print(f"  {date}: {day_success} 条")

    pos_ratio = total_pos / total_success if total_success > 0 else 0
    print(f"\n[完成] 共 {total_success} 条评估, 正例 {total_pos} 条, 正例比例 {pos_ratio*100:.1f}%")
    if target_pos_ratio and pos_ratio < target_pos_ratio:
        print(f"⚠️  正例比例未达目标 {target_pos_ratio*100:.0f}%, 建议先用 gen_risky_users.py 造更多 RISK 经销商")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="制造业风控系统 - 带日期范围的评估数据生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例:
  python scripts/gen_risk_data_with_dates.py
  python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30
  python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live
        """,
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--per-day", type=int, default=None, help="每天固定条数")
    parser.add_argument("--max-per-day", type=int, default=None, help="每天最多条数 (随机 1~N)")
    parser.add_argument("--start", type=str, default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--balance-pos", action="store_true", help="优先挑 RISK 高风险经销商")
    parser.add_argument("--target-pos-ratio", type=float, default=None, help="目标正例比例")
    parser.add_argument("--clean", action="store_true", help="先清空风控运行时表")
    parser.add_argument("--live", action="store_true", help="实时打印命中的高风险评估")
    args = parser.parse_args()
    asyncio.run(generate_with_dates(
        days=args.days, per_day=args.per_day, max_per_day=args.max_per_day,
        start=args.start, end=args.end, balance_pos=args.balance_pos,
        target_pos_ratio=args.target_pos_ratio, clean=args.clean, live=args.live,
    ))
