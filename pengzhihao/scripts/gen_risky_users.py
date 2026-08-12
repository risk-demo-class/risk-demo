"""物流高风险样本入口。

风险用户及其运单由 gen_business_data.py 的固定六类模式统一生成，避免多套造数
逻辑产生不一致数据。
"""
import argparse
import asyncio

from gen_business_data import SEED, load_database
from app.database import async_engine


def main():
    parser = argparse.ArgumentParser(description="重建含六类高风险寄件人的物流业务数据")
    parser.add_argument("--count", type=int, default=30, help="兼容参数，固定模式不依赖此值")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    async def _load_and_close():
        try:
            await load_database(args.seed)
        finally:
            await async_engine.dispose()
    asyncio.run(_load_and_close())


if __name__ == "__main__":
    main()
