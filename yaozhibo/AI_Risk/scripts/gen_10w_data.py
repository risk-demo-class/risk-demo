"""兼容入口：批量生成教育业务事件；推荐直接使用 gen_business_data.py。"""
import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gen_business_data import generate_business_data


async def main() -> int:
    parser = argparse.ArgumentParser(description="批量生成教育风控教学数据")
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260811)
    args = parser.parse_args()
    result = await generate_business_data(args.events, args.seed, run_risk=True)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
