"""把现有教学评估及关联案件均匀分布到最近 N 天。

只修改时间字段，不删除记录、不改变规则结果、评分、决策或模型分数。
用于旧数据全部集中在同一天时修复仪表盘趋势展示。
"""
import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.models import RiskActionLog, RiskAssessment, RiskCase, RiskEvent  # noqa: E402


def _distributed_timestamp(index: int, total: int, days: int, now: datetime) -> datetime:
    """最新记录落在今天，其余记录按轮次均匀分配到之前日期。"""
    day_offset = (total - 1 - index) % days
    target_date = (now - timedelta(days=day_offset)).date()
    max_second = now.hour * 3600 + now.minute * 60 + now.second if day_offset == 0 else 86399
    # 线性同余式提供稳定的日内散布，不依赖全局随机状态。
    second = ((index + 1) * 7919 + days * 104729) % max(1, max_second + 1)
    return datetime.combine(target_date, time.min) + timedelta(seconds=second)


async def spread(days: int) -> tuple[dict[str, int], dict[str, int]]:
    now = datetime.now().replace(microsecond=0)
    async with AsyncSessionLocal() as db:
        assessments = (await db.execute(select(RiskAssessment).order_by(
            RiskAssessment.create_time, RiskAssessment.assessment_id,
        ))).scalars().all()
        if not assessments:
            raise RuntimeError("risk_assessment 没有数据，请先生成训练样本")

        event_by_id = {
            item.event_id: item
            for item in (await db.execute(select(RiskEvent))).scalars().all()
        }
        cases_by_assessment: dict[str, list[RiskCase]] = defaultdict(list)
        case_by_id: dict[str, RiskCase] = {}
        for case_item in (await db.execute(select(RiskCase))).scalars().all():
            cases_by_assessment[case_item.assessment_id].append(case_item)
            case_by_id[case_item.case_id] = case_item
        logs_by_case: dict[str, list[RiskActionLog]] = defaultdict(list)
        for log in (await db.execute(select(RiskActionLog).where(
            RiskActionLog.target_type == "case",
        ))).scalars().all():
            if log.target_id in case_by_id:
                logs_by_case[log.target_id].append(log)

        assessment_counts: dict[str, int] = defaultdict(int)
        case_counts: dict[str, int] = defaultdict(int)
        total = len(assessments)
        for index, assessment in enumerate(assessments):
            timestamp = _distributed_timestamp(index, total, days, now)
            date_key = timestamp.date().isoformat()
            assessment.create_time = timestamp
            assessment_counts[date_key] += 1

            event = event_by_id.get(assessment.event_id)
            if event is not None:
                event.create_time = timestamp

            for case_item in cases_by_assessment.get(assessment.assessment_id, []):
                case_item.create_time = timestamp
                case_item.update_time = timestamp
                if case_item.review_time is not None:
                    case_item.review_time = timestamp + timedelta(minutes=5)
                case_counts[date_key] += 1
                for log in logs_by_case.get(case_item.case_id, []):
                    log.create_time = timestamp + timedelta(minutes=5)

        await db.commit()
        return dict(assessment_counts), dict(case_counts)


async def run(days: int) -> None:
    try:
        assessment_counts, case_counts = await spread(days)
    finally:
        await async_engine.dispose()

    print(f"教学历史时间分布完成: 最近 {days} 天")
    print("日期          评估数   案件数")
    for date_key in sorted(assessment_counts):
        print(f"{date_key}  {assessment_counts[date_key]:>6}   {case_counts.get(date_key, 0):>6}")
    print(f"合计          {sum(assessment_counts.values()):>6}   {sum(case_counts.values()):>6}")


def main() -> None:
    parser = argparse.ArgumentParser(description="把现有教学评估和案件均匀铺到最近N天")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--yes", action="store_true", help="确认修改教学库中的时间字段")
    args = parser.parse_args()
    if not 2 <= args.days <= 365:
        parser.error("--days 必须在 2~365 之间")
    if not args.yes:
        parser.error("该操作会修改现有教学数据的时间字段，请添加 --yes")
    asyncio.run(run(args.days))


if __name__ == "__main__":
    main()
