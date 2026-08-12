"""银行版按日期生成风控评估数据。

为仪表盘生成跨天评估记录。数据来源：bank_transaction、loan_application、login_log。

示例：
    python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50
    python scripts/gen_risk_data_with_dates.py --start 2026-08-06 --end 2026-08-12 --per-day 20
    python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50 --clean
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def clean_risk_runtime_data(db) -> None:
    """清空运行时风控数据，保留业务表、规则和黑名单。"""
    for table_name in [
        "risk_feature", "risk_case", "risk_assessment", "risk_event", "risk_user_profile",
    ]:
        await db.execute(text(f"DELETE FROM {table_name}"))
    await db.commit()


async def load_bank_events(db) -> list[tuple[str, str, str]]:
    """读取可用于评估的银行业务事件，排除会被前置黑名单短路的示例数据。"""
    events: list[tuple[str, str, str]] = []
    queries = [
        ("大额转账", "SELECT txn_id, user_id FROM bank_transaction WHERE txn_id <> 'TX1004'"),
        ("贷款申请", "SELECT loan_id, user_id FROM loan_application"),
        ("异常登录", "SELECT login_id, user_id FROM login_log WHERE ip <> '185.220.10.1'"),
    ]
    for event_type, sql in queries:
        rows = (await db.execute(text(sql))).all()
        events.extend((event_type, str(row[0]), str(row[1])) for row in rows)
    return events


async def backdate_evaluation(db, response, target_time: datetime, user_id: str) -> None:
    """将本次新生成的事件、特征、评估和画像时间回填到指定日期。"""
    await db.execute(
        text("UPDATE risk_event SET create_time = :target_time WHERE event_id = :event_id"),
        {"target_time": target_time, "event_id": response.event_id},
    )
    await db.execute(
        text("UPDATE risk_feature SET compute_time = :target_time WHERE event_id = :event_id"),
        {"target_time": target_time, "event_id": response.event_id},
    )
    await db.execute(
        text("UPDATE risk_assessment SET create_time = :target_time WHERE assessment_id = :assessment_id"),
        {"target_time": target_time, "assessment_id": response.assessment_id},
    )
    await db.execute(
        text("""
            UPDATE risk_user_profile
            SET last_assessment_time = :target_time, update_time = :target_time
            WHERE user_id = :user_id
        """),
        {"target_time": target_time, "user_id": user_id},
    )
    await db.commit()


async def generate(days: int, per_day: int, start: str | None, end: str | None, clean: bool) -> None:
    today = datetime.now().date()
    if start and end:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    elif start:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = start_date + timedelta(days=days - 1)
    else:
        end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else today
        start_date = end_date - timedelta(days=days - 1)

    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")

    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_runtime_data(db)
            print("已清空风控运行时数据")

        events = await load_bank_events(db)
        if not events:
            raise RuntimeError("没有可用的银行业务数据；请先执行 python scripts/init_db.py --reset --yes")

        total = 0
        failures = 0
        current_date = start_date
        while current_date <= end_date:
            day_success = 0
            for index in range(per_day):
                event_type, source_id, user_id = random.choice(events)
                request = RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=user_id,
                    event_data={"generated": True, "backdated": True},
                )
                target_time = datetime.combine(current_date, time(hour=9 + index % 10, minute=index % 60))
                try:
                    response = await process_event(db, request)
                    if response.assessment_id == "blacklist_reject":
                        failures += 1
                        continue
                    await backdate_evaluation(db, response, target_time, user_id)
                    day_success += 1
                    total += 1
                except Exception as exc:
                    await db.rollback()
                    failures += 1
                    print(f"[{current_date}] 跳过 {event_type}/{source_id}: {exc}")
            print(f"[{current_date}] 已生成 {day_success}/{per_day} 条银行评估")
            current_date += timedelta(days=1)

    print(f"完成：{start_date} ~ {end_date}，共生成 {total} 条评估，跳过 {failures} 条")


async def main() -> None:
    parser = argparse.ArgumentParser(description="银行版按日期生成风控评估数据")
    parser.add_argument("--days", type=int, default=7, help="生成最近 N 天，默认 7")
    parser.add_argument("--per-day", type=int, default=50, help="每天生成评估数，默认 50")
    parser.add_argument("--start", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--clean", action="store_true", help="先清空风控运行时数据")
    args = parser.parse_args()
    if args.days < 1 or args.per_day < 1:
        parser.error("--days 和 --per-day 必须大于 0")
    try:
        await generate(args.days, args.per_day, args.start, args.end, args.clean)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
