"""批量生成虚构银行业务 source；保留旧文件名作为兼容入口。"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from scripts.gen_business_data import build_business_data, write_business_data


async def gen_10w_data(
    n_user: int = 10_000,
    min_orders: int = 1,
    max_orders: int = 8,
    n_sku: int = 100,
    batch_size: int = 500,
):
    """每个客户约生成四类银行 source 各一条。"""
    if n_user < 20:
        raise ValueError("n_user 至少为 20")
    data = build_business_data(count=n_user * 4, seed=20260812)
    await write_business_data(data, settings.DB_NAME)
    return data["summary"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量生成虚构银行业务数据")
    parser.add_argument("--users", type=int, default=10_000)
    args = parser.parse_args()
    print(asyncio.run(gen_10w_data(n_user=args.users)))
