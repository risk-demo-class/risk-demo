"""兼容任务书命名：生成含正常、新用户、黄牛和拒签用户的业务数据。"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.gen_business_data import generate

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=120)
    args = parser.parse_args()
    print(asyncio.run(generate(args.count, reset=False)))
