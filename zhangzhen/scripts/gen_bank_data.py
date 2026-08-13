"""生成参数化银行业务数据和候选事件清单。"""

import argparse
import asyncio
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_generation import (  # noqa: E402
    GenerationConfig,
    generate_bank_data,
    pattern_distribution,
    save_manifest,
)
from app.database import AsyncSessionLocal, async_engine  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成可复现的银行风控教学业务数据")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--transactions", type=int, default=20_000)
    parser.add_argument("--loans", type=int, default=500)
    parser.add_argument("--login-min", type=int, default=5)
    parser.add_argument("--login-max", type=int, default=30)
    parser.add_argument("--candidates", type=int, default=2000)
    parser.add_argument("--risk-ratio", type=float, default=0.28)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--prefix", default="BG")
    parser.add_argument("--end-time", default="2026-08-12T23:59:00")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data" / "bank_generation_manifest.json",
    )
    return parser


async def run(args: argparse.Namespace) -> None:
    config = GenerationConfig(
        users=args.users,
        transactions=args.transactions,
        loans=args.loans,
        logins_per_user_min=args.login_min,
        logins_per_user_max=args.login_max,
        candidate_count=args.candidates,
        risk_ratio=args.risk_ratio,
        days=args.days,
        seed=args.seed,
        prefix=args.prefix,
        end_time=args.end_time,
    )
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                summary, candidates = await generate_bank_data(db, config)
        save_manifest(args.manifest, config=config, summary=summary, candidates=candidates)
        print("银行业务数据生成完成：")
        for name, value in asdict(summary).items():
            print(f"  {name}: {value}")
        print("八类候选场景分布：")
        for name, count in pattern_distribution(candidates).items():
            print(f"  {name}: {count}")
        print(f"候选清单：{args.manifest}")
        print("下一步：uv run python scripts/gen_risk_data_with_dates.py")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
