"""按日期批量生成教育风控评估数据，让仪表盘趋势图有最近多天的数据。"""
import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from scripts.gen_risk_data import _load_rows, build_education_requests
from app.service.event import process_event


def build_date_plan(*, days: int, per_day: int, end_day: date) -> list[tuple[date, int]]:
    """返回从最早日期到结束日期的每日生成计划。"""
    if days <= 0:
        raise ValueError("days 必须大于 0")
    if per_day <= 0:
        raise ValueError("per_day 必须大于 0")
    start_day = end_day - timedelta(days=days - 1)
    return [(start_day + timedelta(days=offset), per_day) for offset in range(days)]


async def _clean_risk_runtime_tables(db) -> None:
    """仅在显式传入 --clean 时清除旧的运行数据，不删除规则和教育业务数据。"""
    for table in ("risk_feature", "risk_case", "risk_assessment", "risk_event", "risk_user_profile"):
        await db.execute(text(f"DELETE FROM {table}"))
    await db.commit()


async def generate_risk_data_with_dates(
    *,
    days: int = 7,
    per_day: int = 8,
    end_day: date | None = None,
    clean: bool = False,
) -> int:
    """针对教育报名、退费、打赏事件生成跨日期的风险评估。"""
    end_day = end_day or date.today()
    plan = build_date_plan(days=days, per_day=per_day, end_day=end_day)

    async with AsyncSessionLocal() as db:
        if clean:
            await _clean_risk_runtime_tables(db)

        enrollments, refunds, rewards = await _load_rows(db, max(per_day, 10))
        if not any((enrollments, refunds, rewards)):
            print("没有教育业务数据，请先运行 scripts/gen_business_data.py。")
            return 0

        print(f"按日期生成：{plan[0][0]} 到 {plan[-1][0]}，每天 {per_day} 条。")
        success = 0
        for current_day, day_count in plan:
            requests = build_education_requests(
                enrollments=enrollments,
                refunds=refunds,
                rewards=rewards,
                count=day_count,
            )
            day_success = 0
            for sequence, request in enumerate(requests):
                # 让同一天里的记录也有不同时间，图表只按日期统计。
                target_time = datetime.combine(current_day, datetime.min.time()) + timedelta(
                    hours=(sequence * 3) % 24,
                    minutes=(sequence * 11) % 60,
                )
                try:
                    result = await process_event(db, request)
                    await db.execute(
                        text("UPDATE risk_event SET create_time = :time WHERE event_id = :event_id"),
                        {"time": target_time, "event_id": result.event_id},
                    )
                    await db.execute(
                        text("UPDATE risk_feature SET compute_time = :time WHERE event_id = :event_id"),
                        {"time": target_time, "event_id": result.event_id},
                    )
                    await db.execute(
                        text("UPDATE risk_assessment SET create_time = :time WHERE assessment_id = :assessment_id"),
                        {"time": target_time, "assessment_id": result.assessment_id},
                    )
                    await db.execute(
                        text("UPDATE risk_case SET create_time = :time WHERE assessment_id = :assessment_id"),
                        {"time": target_time, "assessment_id": result.assessment_id},
                    )
                    await db.commit()
                    success += 1
                    day_success += 1
                except Exception as exc:
                    await db.rollback()
                    print(f"  {current_day} {request.source_id} 失败：{exc}")
            print(f"  {current_day}：成功 {day_success}/{day_count} 条")

    print(f"完成：共生成 {success} 条跨日期评估记录。刷新仪表盘即可看到趋势图。")
    return success


async def _runner(args) -> None:
    try:
        if args.start or args.end:
            start_day = date.fromisoformat(args.start) if args.start else None
            end_day = date.fromisoformat(args.end) if args.end else date.today()
            days = (end_day - start_day).days + 1 if start_day else args.days
        else:
            end_day = date.today()
            days = args.days
        await generate_risk_data_with_dates(
            days=days,
            per_day=args.per_day,
            end_day=end_day,
            clean=args.clean,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="按日期生成教育风控数据")
    parser.add_argument("--days", type=int, default=7, help="生成最近几天的数据，默认 7")
    parser.add_argument("--per-day", type=int, default=8, help="每天生成几条，默认 8")
    parser.add_argument("--start", type=str, help="起始日期，例如 2026-08-06")
    parser.add_argument("--end", type=str, help="结束日期，例如 2026-08-12")
    parser.add_argument("--clean", action="store_true", help="先删除旧风控运行数据（谨慎使用）")
    args = parser.parse_args()
    asyncio.run(_runner(args))
