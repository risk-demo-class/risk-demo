"""把银行业务流水转换为风控训练样本。

每个业务事件经过与在线接口相同的 process_event 四步编排和 run_risk_check
七步决策链，因此 risk_event/risk_feature/risk_assessment 可直接用于训练。
"""
import argparse
import asyncio
import math
import random
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select, update

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.ml_model import unload_model  # noqa: E402
from app.models import (  # noqa: E402
    BankTransaction,
    LoanApplication,
    LoginLog,
    RiskActionLog,
    RiskAssessment,
    RiskCase,
    RiskEvent,
)
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402


async def load_sources() -> list[tuple[str, str, str]]:
    async with AsyncSessionLocal() as db:
        txns = (await db.execute(select(
            BankTransaction.txn_type, BankTransaction.txn_id, BankTransaction.user_id,
        ))).all()
        loans = (await db.execute(select(
            LoanApplication.loan_id, LoanApplication.user_id,
        ))).all()
        logins = (await db.execute(select(
            LoginLog.login_id, LoginLog.user_id,
        ))).all()
    rows = [(r.txn_type, r.txn_id, r.user_id) for r in txns]
    rows.extend(("贷款", r.loan_id, r.user_id) for r in loans)
    rows.extend(("登录", r.login_id, r.user_id) for r in logins)
    return rows


def _history_timestamp(index: int, days: int, seed: int, now: datetime | None = None) -> datetime:
    """把第 index 条样本稳定分配到最近 days 天，今天不会产生未来时间。"""
    now = (now or datetime.now()).replace(microsecond=0)
    day_offset = (index - 1) % days
    target_date = (now - timedelta(days=day_offset)).date()
    max_second = now.hour * 3600 + now.minute * 60 + now.second if day_offset == 0 else 86399
    rng = random.Random(seed * 1_000_003 + index)
    second = rng.randint(0, max(0, max_second))
    return datetime.combine(target_date, time.min) + timedelta(seconds=second)


async def _set_history_time(db, result, timestamp: datetime) -> int:
    """同步回写事件、评估、案件和自动审核日志时间，保持审计链一致。"""
    await db.execute(update(RiskEvent).where(
        RiskEvent.event_id == result.event_id,
    ).values(create_time=timestamp))
    await db.execute(update(RiskAssessment).where(
        RiskAssessment.assessment_id == result.assessment_id,
    ).values(create_time=timestamp))
    cases = (await db.execute(select(RiskCase).where(
        RiskCase.assessment_id == result.assessment_id,
    ))).scalars().all()
    case_ids = []
    for case_item in cases:
        case_item.create_time = timestamp
        case_item.update_time = timestamp
        if case_item.review_time is not None:
            case_item.review_time = timestamp + timedelta(minutes=5)
        case_ids.append(case_item.case_id)
    if case_ids:
        await db.execute(update(RiskActionLog).where(
            RiskActionLog.target_type == "case",
            RiskActionLog.target_id.in_(case_ids),
        ).values(create_time=timestamp + timedelta(minutes=5)))
    await db.commit()
    return len(case_ids)


async def generate(repeats: int, seed: int, samples: int, days: int) -> None:
    sources = await load_sources()
    if not sources:
        raise SystemExit("没有银行业务数据，请先运行 init_db.py 或 gen_business_data.py")
    # 当 --samples 大于“业务源数量 × repeats”时自动增加轮数，保证精确生成请求数量。
    effective_repeats = max(repeats, math.ceil(samples / len(sources))) if samples > 0 else repeats
    plan = sources * effective_repeats
    random.Random(seed).shuffle(plan)
    if samples > 0:
        plan = plan[:samples]
    success = 0
    failed = 0
    cases_created = 0
    daily_counts: dict[str, int] = {}
    for index, (event_type, source_id, user_id) in enumerate(plan, 1):
        try:
            async with AsyncSessionLocal() as db:
                result = await process_event(db, RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=user_id,
                    event_data={"dataset_round": index},
                ))
                if days > 1:
                    timestamp = _history_timestamp(index, days, seed)
                    cases_created += await _set_history_time(db, result, timestamp)
                    date_key = timestamp.date().isoformat()
                    daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
            success += 1
        except Exception as exc:
            failed += 1
            print(f"[WARN] {event_type}/{source_id}: {exc}")
        if index % 100 == 0:
            print(f"进度 {index}/{len(plan)}，成功 {success}，失败 {failed}")
    print(f"训练样本生成完成: 计划 {len(plan)}，成功 {success}，失败 {failed}")
    if daily_counts:
        print(f"历史时间分布: 最近 {days} 天，关联案件 {cases_created} 个")
        for date_key in sorted(daily_counts):
            print(f"  {date_key}: {daily_counts[date_key]} 条评估")


def main() -> None:
    parser = argparse.ArgumentParser(description="通过真实银行决策链生成训练样本")
    parser.add_argument("--repeats", type=int, default=12, help="每条业务流水重复评估次数")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--samples", "--limit", dest="samples", type=int, default=1000,
        help="生成的训练评估数；--limit 为兼容旧命令的别名，0表示不限制",
    )
    parser.add_argument("--days", type=int, default=1, help="按最近N天分布评估与案件时间，默认1天")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats 必须 >= 1")
    if args.samples < 0:
        parser.error("--samples 必须 >= 0")
    if not 1 <= args.days <= 365:
        parser.error("--days 必须在 1~365 之间")
    # 训练标签必须来自规则决策，不能混入已有XGBoost模型的预测结果。
    unload_model()
    print("训练样本模式: XGBoost 已禁用，本轮使用纯规则生成标签 (ml_score=NULL)")
    async def run_and_cleanup() -> None:
        try:
            await generate(args.repeats, args.seed, args.samples, args.days)
        finally:
            # 必须在 asyncio.run() 关闭事件循环前释放 aiomysql 连接池。
            await async_engine.dispose()

    asyncio.run(run_and_cleanup())


if __name__ == "__main__":
    main()
