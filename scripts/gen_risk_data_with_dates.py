"""
制造业风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据, 让仪表盘趋势图有跨天数据.

用法:
    # 默认: 近 7 天, 每天随机 1~30 条
    python scripts/gen_risk_data_with_dates.py

    # 近 30 天, 每天固定 200 条, 循环造到正例 30% (训练用, 推荐)
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30

    # 造"今日"数据 (仪表盘今日能看到)
    python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live
"""
import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows GBK 终端不能编码 emoji, 强制 stdout UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.service.event import process_event
from scripts.mfg_pickers import build_request, pick_random_event

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
                "risk_case", "risk_user_profile"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败: {e}")
    await db.commit()


async def backdate_record(db, table: str, time_col: str, event_id: str, target_time: datetime):
    """把指定记录的某个时间字段改写成目标时间."""
    id_col = (
        'event_id' if 'event' in table
        else 'assessment_id' if 'assess' in table
        else 'case_id' if 'case' in table
        else 'user_id'
    )
    await db.execute(
        text(f"UPDATE {table} SET {time_col} = :t WHERE {id_col} = :eid"),
        {"t": target_time, "eid": event_id},
    )


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
    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.now()
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        else:
            start_dt = (end_dt - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0)

        if target_pos_ratio is not None and not balance_pos:
            print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险经销商")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%")
        if live:
            print("📌 --live 模式: 不回写 create_time, 数据 create_time=now")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_total = 0
        grand_success = 0
        grand_reject = 0
        grand_positive = 0

        for day_offset in range(total_days):
            current_date = start_dt.date() + timedelta(days=day_offset)
            day_count = per_day if per_day is not None else random.randint(1, max_per_day)
            print(f"[{current_date}] 生成 {day_count} 条评估...")

            day_success = 0
            day_reject = 0
            day_positive = 0

            for i in range(day_count):
                random_hour = random.randint(0, 23)
                random_minute = random.randint(0, 59)
                random_second = random.randint(0, 59)
                target_time = datetime.combine(
                    current_date, datetime.min.time()
                ).replace(hour=random_hour, minute=random_minute, second=random_second)

                picked = await pick_random_event(db, balance_pos)
                if not picked:
                    continue
                event_type, source_id, user_id, order_id = picked
                request = build_request(event_type, source_id, user_id, order_id)

                try:
                    await process_event(db, request)
                    backdate_target = None if live else target_time

                    new_event = (await db.execute(text("""
                        SELECT event_id FROM risk_event
                        WHERE user_id = :uid ORDER BY create_time DESC LIMIT 1
                    """), {"uid": request.user_id})).first()
                    new_assess = (await db.execute(text("""
                        SELECT assessment_id, decision FROM risk_assessment
                        WHERE user_id = :uid ORDER BY create_time DESC LIMIT 1
                    """), {"uid": request.user_id})).first()

                    if new_event and backdate_target is not None:
                        await backdate_record(db, "risk_event", "create_time", new_event.event_id, backdate_target)
                        await db.execute(
                            text("UPDATE risk_feature SET compute_time = :t WHERE event_id = :eid"),
                            {"t": backdate_target, "eid": new_event.event_id},
                        )
                    if new_assess:
                        if backdate_target is not None:
                            await backdate_record(db, "risk_assessment", "create_time", new_assess.assessment_id, backdate_target)
                            await db.execute(
                                text("UPDATE risk_case SET create_time = :t WHERE assessment_id = :aid"),
                                {"t": backdate_target, "aid": new_assess.assessment_id},
                            )
                        if new_assess.decision in ("拒绝", "人工审核"):
                            day_positive += 1
                            grand_positive += 1

                    await db.execute(
                        text("UPDATE risk_user_profile SET last_assessment_time = :t, update_time = :t WHERE user_id = :uid"),
                        {"t": backdate_target or datetime.now(), "uid": request.user_id},
                    )
                    await db.commit()
                    day_success += 1
                    grand_success += 1
                except Exception as e:
                    await db.rollback()
                    day_reject += 1
                    grand_reject += 1
                    _log_failure(target_time, request, e)

            print(f"  -> 成功 {day_success}, 失败 {day_reject}, 正例 {day_positive}")
            grand_total += day_count

            if target_pos_ratio is not None and day_success > 0:
                current_pos_ratio = day_positive / day_success
                if current_pos_ratio < target_pos_ratio * 0.7:
                    print(f"  ⚠️  今日正例比例 {current_pos_ratio*100:.1f}% < 目标 70%, 检查 RISK 经销商是否存在")

        print(f"\n{'=' * 50}")
        overall_pos = grand_positive / grand_success * 100 if grand_success else 0
        print(f"完成! 总计 {grand_total} 次, 成功 {grand_success}, 失败 {grand_reject}, 正例 {grand_positive} ({overall_pos:.1f}%)")
        if grand_reject > 0:
            print(f"失败详情见: {FAIL_LOG}")
        if overall_pos < 15 and grand_success > 0:
            print(f"⚠️  正例比例仅 {overall_pos:.1f}%, 建议 --balance-pos --target-pos-ratio 0.30 重造")
        print("刷新仪表盘: http://localhost:8000/")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="带日期范围的造数据脚本 (每天条数: --per-day 固定, 或随机 1~--max-per-day)"
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None, help="每天固定条数")
    parser.add_argument("--max-per-day", type=int, default=30, help="每天最多条数")
    parser.add_argument("--clean", action="store_true", help="先清空风控表")
    parser.add_argument("--live", action="store_true", help="不回写 create_time")
    parser.add_argument("--balance-pos", action="store_true", help="80%% 概率挑 RISK 高风险经销商")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos")
    args = parser.parse_args()

    async def _runner():
        from app.database import async_engine
        try:
            await generate_risk_data_with_dates(
                days=args.days,
                per_day=args.per_day,
                max_per_day=args.max_per_day,
                start_date=args.start,
                end_date=args.end,
                clean=args.clean,
                balance_pos=args.balance_pos,
                target_pos_ratio=args.target_pos_ratio,
                live=args.live,
            )
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())
