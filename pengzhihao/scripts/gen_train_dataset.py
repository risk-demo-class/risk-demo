"""生成物流 XGBoost 训练集：调用真实风控管道保存 25 维特征快照。"""
import argparse
import asyncio

from gen_risk_data import generate_risk_data


def main():
    parser = argparse.ArgumentParser(description="生成物流训练数据")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--count", type=int, default=None)
    args = parser.parse_args()
    async def _generate_and_close():
        from app.database import async_engine
        try:
            await generate_risk_data(count=args.count, reset=args.reset)
        finally:
            await async_engine.dispose()
    asyncio.run(_generate_and_close())


if __name__ == "__main__":
    main()
