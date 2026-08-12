"""兼容入口：物流评估时间直接使用当前风险流水时间。"""
import argparse
import asyncio

from gen_risk_data import generate_risk_data


def main():
    parser = argparse.ArgumentParser(description="生成物流风险评估")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--count", type=int)
    args, _ = parser.parse_known_args()
    asyncio.run(generate_risk_data(args.count, reset=args.clean or args.reset))


if __name__ == "__main__":
    main()
