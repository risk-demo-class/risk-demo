"""按业务发生时间回放候选事件，调用真实 process_event 生成评估数据。"""

import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.data_generation import load_manifest  # noqa: E402
from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.ml_model import ml_model  # noqa: E402
from app.models import EventType  # noqa: E402
from app.models_risk import RiskEvent  # noqa: E402
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="跨日期生成真实风控评估与 25 维特征快照")
    parser.add_argument(
        "--manifest", type=Path,
        default=PROJECT_ROOT / "data" / "bank_generation_manifest.json",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 表示回放清单中的全部事件")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--allow-model",
        action="store_true",
        help="默认关闭模型以保持训练标签纯度；指定后允许模型参与回放",
    )
    return parser


async def run(args: argparse.Namespace) -> None:
    candidates = sorted(load_manifest(args.manifest), key=lambda item: item.event_time)
    if args.limit > 0:
        candidates = candidates[: args.limit]
    counters: Counter[str] = Counter()
    old_xgb_enabled = settings.XGB_ENABLED
    if not args.allow_model:
        settings.XGB_ENABLED = False
        ml_model.reset()
    try:
        async with AsyncSessionLocal() as db:
            for index, candidate in enumerate(candidates, start=1):
                event_type = EventType(candidate.event_type)
                existing = (
                    await db.execute(
                        select(RiskEvent.event_id).where(
                            RiskEvent.event_type == event_type,
                            RiskEvent.event_source_id == candidate.source_id,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                # SQLAlchemy 的 SELECT 也会自动开启事务；真实 process_event 自己管理
                # 原子写事务，因此在进入它之前先结束这里只读的存在性检查事务。
                await db.rollback()
                if existing is not None:
                    counters["已存在跳过"] += 1
                    continue
                request = RiskCheckRequest.model_validate(candidate.request_data())
                result = await process_event(
                    db,
                    request,
                    decision_time=datetime.fromisoformat(candidate.event_time),
                )
                counters[result.decision.value] += 1
                if index % args.progress_every == 0:
                    print(f"已回放 {index}/{len(candidates)} 条")
        print(f"跨日期回放完成：{len(candidates)} 条候选事件")
        for name, count in counters.items():
            print(f"  {name}: {count}")
        print("下一步：uv run python scripts/gen_train_dataset.py")
    finally:
        settings.XGB_ENABLED = old_xgb_enabled
        ml_model.reset()
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
