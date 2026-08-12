"""大批量物流数据入口（教学版固定为确定性 300 运单样本）。"""
import argparse
import asyncio

from gen_business_data import SEED, load_database


def main():
    parser = argparse.ArgumentParser(description="生成物流业务样本")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--users", type=int, help="兼容参数，当前固定80用户")
    args, _ = parser.parse_known_args()
    asyncio.run(load_database(args.seed))


if __name__ == "__main__":
    main()
