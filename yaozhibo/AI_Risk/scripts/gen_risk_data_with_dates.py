"""兼容入口：按天数估算数量后生成教育风控事件。"""
import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gen_business_data import generate_business_data


async def main() -> int:
    parser = argparse.ArgumentParser(description="生成教育风控事件（日期兼容入口）")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-day", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--balance-pos", action="store_true")
    parser.add_argument("--target-pos-ratio", type=float)
    parser.add_argument("--force-pos-ratio", type=float)
    args = parser.parse_args()
    events = max(100, args.days * args.per_day)
    result = await generate_business_data(events, args.seed, run_risk=True)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
