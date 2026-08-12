"""安全、幂等地创建医疗风控数据库与 17 张表。"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

import pymysql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402  注册全部 ORM 表
from app.service.auth import ensure_default_admin  # noqa: E402


_SAFE_DB_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def _validated_db_name(name: str) -> str:
    if not _SAFE_DB_NAME.fullmatch(name):
        raise ValueError("数据库名只能包含字母、数字和下划线")
    return name


def ensure_database_exists(db_name: str) -> None:
    """只执行 CREATE DATABASE IF NOT EXISTS，不删除任何现有库。"""
    safe_name = _validated_db_name(db_name)
    connection = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{safe_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
    finally:
        connection.close()


async def create_tables(db_name: str) -> None:
    engine = create_async_engine(settings.get_database_url_async(db_name), pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            await ensure_default_admin(db)
    finally:
        await engine.dispose()


async def initialize(db_name: str) -> None:
    ensure_database_exists(db_name)
    await create_tables(db_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化医疗风控数据库（幂等、不删库）")
    parser.add_argument("--db-name", default=settings.DB_NAME, help="目标数据库名")
    parser.add_argument("--yes", action="store_true", help="非交互确认")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_name = _validated_db_name(args.db_name)
    if not args.yes:
        answer = input(f"将幂等创建数据库 `{db_name}` 及缺失表，不删除现有数据。继续? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("已取消")
            return 1
    asyncio.run(initialize(db_name))
    print(f"初始化完成: {db_name}，ORM 已注册 {len(Base.metadata.tables)} 张表")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
