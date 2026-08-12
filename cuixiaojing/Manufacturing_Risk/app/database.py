"""数据库连接层 (全异步)"""
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


# 异步引擎 (主代码 + scripts 全部使用)
async_engine = create_async_engine(
    settings.get_database_url_async(),
    pool_pre_ping=False,
    pool_recycle=3600,  # 1 小时回收, 避开 MySQL wait_timeout
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
    """用法: db: AsyncSession = Depends(get_db_async).

    显式 try/finally + 显式 rollback + 显式 close:
    不依赖 async with 的隐式 aexit (会触发 aiomysql 跨 event loop 时的 Event loop is closed).
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


# ============================================================
# Demo: 展示异步引擎 + 依赖注入 — 真实连 DB
# 跑法: python -m app.database
# ============================================================
if __name__ == "__main__":
    import asyncio
    from sqlalchemy import text

    print("=" * 60)
    print("数据库连接 — 异步引擎演示")
    print("=" * 60)

    print(f"\n[1] 引擎信息:")
    print(f"  async_engine URL    = {async_engine.url}")
    print(f"  driver              = {async_engine.url.drivername}")

    print(f"\n[2] 异步 ping (用 async_engine):")
    async def _async_ping():
        async with async_engine.begin() as conn:
            r = await conn.execute(text("SELECT 1+1 AS two"))
            return r.scalar()
    try:
        v = asyncio.run(_async_ping())
        print(f"  SELECT 1+1         = {v}  (异步 OK)")
    except Exception as e:
        print(f"  [WARN] 异步连不上: {e}")

    print("\n" + "=" * 60)
    print("建表: python scripts/init_db.py --yes")
    print("造数: python scripts/gen_data.py")
