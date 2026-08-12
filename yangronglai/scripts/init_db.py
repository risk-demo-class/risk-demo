"""Initialize the stage-2/3 database and idempotent seed data."""

import argparse
import asyncio

from app.bootstrap import drop_schema, initialize_database
from app.database import close_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize BankRisk-AI database")
    parser.add_argument("--no-demo", action="store_true", help="只初始化表结构和 8 条规则")
    parser.add_argument("--reset", action="store_true", help="先删除当前配置数据库中的全部项目表")
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    try:
        if args.reset:
            await drop_schema()
        result = await initialize_database(seed_demo=not args.no_demo)
        print(f"数据库初始化完成: {result}")
        return 0
    finally:
        await close_database()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
