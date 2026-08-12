"""初始化 8 张银行业务表和 9 张风控核心表。

示例：
    python scripts/init_db.py
    python scripts/init_db.py --reset --yes
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import async_engine, create_all_tables, drop_all_tables, ping_database  # noqa: E402
from app.models import Base  # noqa: E402


SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


async def ensure_mysql_database() -> None:
    """在建表前确保目标 MySQL 数据库存在。"""

    target_url = settings.get_database_url_async()
    if not target_url.startswith("mysql+"):
        return
    if not SAFE_DATABASE_NAME.fullmatch(settings.DB_NAME):
        raise ValueError("DB_NAME 只能包含字母、数字和下划线")

    server_url = URL.create(
        drivername="mysql+aiomysql",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        query={"charset": "utf8mb4"},
    )
    server_engine = create_async_engine(server_url, pool_pre_ping=True)
    try:
        async with server_engine.begin() as connection:
            await connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
            )
    finally:
        await server_engine.dispose()


async def initialize(reset: bool) -> None:
    await ensure_mysql_database()
    if reset:
        await drop_all_tables()
    await create_all_tables()
    await ping_database()
    print(f"数据库初始化成功：{len(Base.metadata.tables)} 张表（8 张业务表 + 9 张风控表）")


async def initialize_and_close(reset: bool) -> None:
    """确保引擎在创建它的同一个事件循环中关闭。"""

    try:
        await initialize(reset)
    finally:
        await async_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化银行风控数据库")
    parser.add_argument("--reset", action="store_true", help="先删除现有 17 张表再重建")
    parser.add_argument("--yes", action="store_true", help="确认允许执行 --reset")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.reset and not args.yes:
        raise SystemExit("重置会删除现有表，请同时传入 --yes 明确确认")
    asyncio.run(initialize_and_close(reset=args.reset))


if __name__ == "__main__":
    main()
