"""Create the configured PP_Risk MySQL database if it does not exist."""

from __future__ import annotations

import asyncio
import re

import aiomysql

from app.config import settings


_MYSQL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


async def create_database() -> None:
    database = settings.DB_NAME
    if settings.DATABASE_URL:
        return
    if not _MYSQL_IDENTIFIER.fullmatch(database):
        raise ValueError("DB_NAME may contain only letters, numbers, and underscores")

    connection = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
                "WHERE SCHEMA_NAME = %s",
                (database,),
            )
            if await cursor.fetchone() is None:
                await cursor.execute(
                    f"CREATE DATABASE `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
    finally:
        connection.close()


def main() -> int:
    asyncio.run(create_database())
    print(f"MySQL database ready: {settings.DB_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
