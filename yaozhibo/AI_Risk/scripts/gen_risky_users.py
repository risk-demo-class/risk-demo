"""兼容入口：生成包含B～F固定风险场景的教育数据。"""
import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gen_business_data import generate_business_data


async def main() -> int:
    parser = argparse.ArgumentParser(description="生成教育高风险演示用户")
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--seed", type=int, default=20260811)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count 必须至少为1")
    result = await generate_business_data(max(150, args.count * 20), args.seed, run_risk=True)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
