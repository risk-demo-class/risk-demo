"""批量生成教育风控评估记录，用于填充仪表盘和案件页面。"""
import argparse
import asyncio
import os
import sys
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event


EventRow = tuple[str, str]


def build_education_requests(
    *,
    enrollments: Sequence[EventRow],
    refunds: Sequence[EventRow],
    rewards: Sequence[EventRow],
    count: int,
) -> list[RiskCheckRequest]:
    """把三类业务记录，轮流变成可送进风控引擎的请求。"""
    groups = [
        ("课程报名", enrollments),
        ("退费申请", refunds),
        ("直播打赏", rewards),
    ]
    groups = [(event_type, rows) for event_type, rows in groups if rows]
    if count <= 0 or not groups:
        return []

    requests: list[RiskCheckRequest] = []
    round_index = 0
    while len(requests) < count:
        for event_type, rows in groups:
            source_id, user_id = rows[round_index % len(rows)]
            requests.append(
                RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=user_id,
                    event_data={"generated_by": "scripts/gen_risk_data.py"},
                )
            )
            if len(requests) == count:
                break
        round_index += 1
    return requests


async def _load_rows(db, limit: int) -> tuple[list[EventRow], list[EventRow], list[EventRow]]:
    # 优先使用 gen_business_data.py 生成的报名记录；没有时才取已有的全部报名记录。
    enrollment_result = await db.execute(text("""
        SELECT enrollment_id, user_id
        FROM enrollment
        ORDER BY CASE WHEN enrollment_id LIKE 'edu_demo_%' THEN 0 ELSE 1 END, RAND()
        LIMIT :limit
    """), {"limit": limit})
    refund_result = await db.execute(text("""
        SELECT refund_id, user_id FROM refund_request ORDER BY RAND() LIMIT :limit
    """), {"limit": limit})
    reward_result = await db.execute(text("""
        SELECT reward_id, user_id FROM live_reward ORDER BY RAND() LIMIT :limit
    """), {"limit": limit})
    return (
        [(row[0], row[1]) for row in enrollment_result.all()],
        [(row[0], row[1]) for row in refund_result.all()],
        [(row[0], row[1]) for row in reward_result.all()],
    )


async def generate_risk_data(count: int = 30) -> int:
    """执行 count 次教育事件风险评估，返回成功数。"""
    async with AsyncSessionLocal() as db:
        enrollments, refunds, rewards = await _load_rows(db, max(count, 10))
        requests = build_education_requests(
            enrollments=enrollments,
            refunds=refunds,
            rewards=rewards,
            count=count,
        )
        if not requests:
            print("没有可用的教育业务数据。请先运行 scripts/gen_business_data.py。")
            return 0

        print(f"开始自动生成 {len(requests)} 条教育风控评估记录...")
        success = 0
        for index, request in enumerate(requests, start=1):
            try:
                result = await process_event(db, request)
                await db.commit()
                success += 1
                print(
                    f"  [{index}/{len(requests)}] {request.event_type} "
                    f"{request.source_id}: {result.final_score} 分，{result.decision}"
                )
            except Exception as exc:
                await db.rollback()
                print(f"  [{index}/{len(requests)}] {request.source_id} 失败：{exc}")

        print(f"完成：成功生成 {success}/{len(requests)} 条评估记录。")
        return success


async def _runner(count: int) -> None:
    try:
        await generate_risk_data(count)
    finally:
        # Windows 下显式关闭连接池，避免退出时出现 Event loop is closed 警告。
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量生成教育风控评估记录")
    parser.add_argument("--count", type=int, default=30, help="生成条数，默认 30")
    args = parser.parse_args()
    asyncio.run(_runner(args.count))
