"""
旅游风控系统 - 按日期分布的风控评估数据生成

在 gen_risk_data.py 基础上, 把评估记录 create_time 回写到过去 N 天,
让仪表盘趋势 / 训练数据时间跨度更真实.

用法:
  python scripts/gen_risk_data_with_dates.py --days 30 --per-day 50
  python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30
  python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live   # 不回写时间 (今天)
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from scripts.gen_risk_data import generate_risk_data  # noqa: E402


async def _clean_risk_data(db) -> None:
    """清空风控评估相关表 (重造前用)."""
    for table in ("risk_case", "risk_assessment", "risk_feature", "risk_event", "risk_user_profile"):
        await db.execute(text(f"DELETE FROM {table}"))
    await db.commit()
    print("已清空 risk_event/feature/assessment/case/user_profile")


async def _backdate(day_offset: int) -> None:
    """把最近一批评估记录的时间回写到 N 天前."""
    target = datetime.now() - timedelta(days=day_offset)
    ts = target.strftime("%Y-%m-%d %H:%M:%S")
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE risk_event SET create_time = :ts WHERE create_time >= NOW() - INTERVAL 1 DAY"
        ), {"ts": ts})
        await db.execute(text(
            "UPDATE risk_assessment SET create_time = :ts WHERE create_time >= NOW() - INTERVAL 1 DAY"
        ), {"ts": ts})
        await db.execute(text(
            "UPDATE risk_case SET create_time = :ts WHERE create_time >= NOW() - INTERVAL 1 DAY"
        ), {"ts": ts})
        await db.execute(text(
            "UPDATE risk_feature SET compute_time = :ts WHERE compute_time >= NOW() - INTERVAL 1 DAY"
        ), {"ts": ts})
        await db.commit()


async def main(args) -> None:
    days = args.days
    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d")
        end = datetime.strptime(args.end, "%Y-%m-%d")
        days = max((end - start).days + 1, 1)
    per_day = min(args.per_day, args.max_per_day) if args.max_per_day else args.per_day

    async with AsyncSessionLocal() as db:
        if args.clean:
            await _clean_risk_data(db)

    total = 0
    for offset in range(days - 1, -1, -1):
        print(f"\n{'=' * 50}\n第 {days - offset}/{days} 天 (回写 {offset} 天前), 生成 {per_day} 条")
        await generate_risk_data(
            count=per_day,
            balance_pos=args.balance_pos,
            target_pos_ratio=None if offset < days - 1 else args.target_pos_ratio,
        )
        total += per_day
        if not args.live and offset > 0:
            await _backdate(offset)

    print(f"\n完成! 共生成约 {total} 条评估记录, 时间跨度 {days} 天")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="按日期生成旅游风控评估数据")
    parser.add_argument("--days", type=int, default=30, help="回溯天数 (默认 30)")
    parser.add_argument("--per-day", type=int, default=50, help="每天评估条数 (默认 50)")
    parser.add_argument("--max-per-day", type=int, default=None, help="每天上限 (可选)")
    parser.add_argument("--clean", action="store_true", help="先生成前清空评估数据")
    parser.add_argument("--start", type=str, default=None, help="开始日期 YYYY-MM-DD (替代 --days)")
    parser.add_argument("--end", type=str, default=None, help="结束日期 YYYY-MM-DD (替代 --days)")
    parser.add_argument("--balance-pos", action="store_true", help="优先挑 RISK 高风险用户")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (配合 --balance-pos)")
    parser.add_argument("--live", action="store_true", help="不回写 create_time (今天的数据)")
    args = parser.parse_args()

    async def _runner():
        try:
            await main(args)
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())
