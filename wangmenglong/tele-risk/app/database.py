"""
电信风控系统 - 数据库连接层 (全异步)

参照 ai_risk/app/database.py:
  - DeclarativeBase 基类
  - 异步引擎 (aiomysql)
  - 显式 try/finally 的 get_db_async 依赖注入
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# 所有 ORM 模型的公共基类
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
    """FastAPI 依赖注入: db: AsyncSession = Depends(get_db_async).

    显式 try/finally + rollback + close, 避开 aiomysql 跨 event loop 的
    'Event loop is closed' 问题. 业务代码负责 commit.
    """
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


if __name__ == "__main__":
    import asyncio
    from sqlalchemy import text

    async def _ping():
        async with async_engine.begin() as conn:
            return await conn.execute(text("SELECT 1+1 AS two"))

    print("=" * 60)
    print("telecom 数据库连接演示")
    print(f"  URL = {async_engine.url}")
    print("=" * 60)
    try:
        r = asyncio.run(_ping())
        print(f"  SELECT 1+1 = {r.scalar()}  (异步连接 OK)")
    except Exception as e:
        print(f"  [WARN] 连不上: {e}")
