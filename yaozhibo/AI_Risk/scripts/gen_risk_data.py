"""兼容入口：生成教育业务事件并运行完整风控流水线。"""
import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gen_business_data import generate_business_data


async def main() -> int:
    parser = argparse.ArgumentParser(description="生成教育风控评估数据")
    parser.add_argument("count", nargs="?", type=int)
    parser.add_argument("--count", dest="count_option", type=int)
    parser.add_argument("--events", type=int)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--balance-pos", action="store_true", help="兼容旧参数；教育生成器已固定风险比例")
    args = parser.parse_args()
    events = args.events or args.count_option or args.count or 150
    result = await generate_business_data(events, args.seed, run_risk=True)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
