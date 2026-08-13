"""从 risk_feature 决策时快照导出严格 25 维训练集。"""

import argparse
import asyncio
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.training import (  # noqa: E402
    export_training_csv,
    load_training_samples,
    validate_training_samples,
)


async def run(args: argparse.Namespace) -> None:
    try:
        async with AsyncSessionLocal() as db:
            samples = await load_training_samples(db, limit=args.limit or None)
        report = validate_training_samples(
            samples,
            min_samples=args.min_samples,
            min_positive_ratio=args.min_positive_ratio,
            max_positive_ratio=args.max_positive_ratio,
            min_span_days=args.min_span_days,
        )
        export_training_csv(args.output, samples)
        print("训练数据纯度校验通过：")
        for name, value in asdict(report).items():
            print(f"  {name}: {value}")
        print(f"已导出：{args.output}")
        print("注意：label 来自规则/合成风险模式，只用于教学，不代表真实欺诈标签。")
    finally:
        await async_engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出并校验 XGBoost 训练数据")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-samples", type=int, default=1250)
    parser.add_argument("--min-positive-ratio", type=float, default=0.15)
    parser.add_argument("--max-positive-ratio", type=float, default=0.60)
    parser.add_argument("--min-span-days", type=int, default=30)
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "data" / "training_dataset.csv",
    )
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
