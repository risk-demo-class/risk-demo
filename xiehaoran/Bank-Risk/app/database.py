"""数据库连接层 (全异步, MySQL + aiomysql)"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


# 异步引擎
async_engine = create_async_engine(
    settings.get_database_url_async(),
    pool_pre_ping=False,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

# 异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_async() -> AsyncGenerator[AsyncSession, None]:
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await db.close()
        except Exception:
            pass


def get_test_engine_async(db_name: str | None = None):
    name = db_name or settings.DB_NAME
    return create_async_engine(
        settings.get_database_url_async(name),
        pool_pre_ping=False,
        pool_recycle=3600,
        echo=False,
    )


if __name__ == "__main__":
    import asyncio
    from sqlalchemy import text

    print("=" * 60)
    print("数据库连接 — 异步引擎演示")
    print("=" * 60)
    print(f"\n[1] 引擎信息:")
    print(f"  async_engine URL = {async_engine.url}")
    print(f"  driver           = {async_engine.url.drivername}")

    async def _async_ping():
        async with async_engine.begin() as conn:
            return await conn.execute(text("SELECT 1+1 AS two"))

    try:
        v = asyncio.run(_async_ping())
        print(f"  SELECT 1+1      = {v.scalar()}  (异步 OK)")
    except Exception as e:
        print(f"  [WARN] 异步连不上: {e}")
    print("\n建表: python scripts/init_db.py --yes")
