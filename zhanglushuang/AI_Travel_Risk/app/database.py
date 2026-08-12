"""
旅游出行风控系统 - 数据库连接层 (全异步).

设计要点:
1. 连接池: pool_size=10, max_overflow=20, 每小时回收连接.
2. pool_pre_ping=True: 取连接前先探测, 避免拿死连接.
3. get_db_async 显式 rollback / close, 不依赖隐式上下文退出.
4. 所有创建 / 检查 / 释放操作都带异常捕获与日志.
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类."""


def _create_async_engine(url: str | None = None) -> AsyncEngine:
    """创建异步引擎, 配置或连接串异常时记录日志并上抛."""
    try:
        engine_url = url or settings.get_database_url_async()
        engine = create_async_engine(
            engine_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
        logger.info(
            "异步数据库引擎创建完成: driver=%s, pool_size=10, max_overflow=20",
            engine.url.drivername,
        )
        return engine
    except Exception as exc:
        logger.exception("异步数据库引擎创建失败: %s", exc)
        raise


# 主流程使用的异步引擎
async_engine = _create_async_engine()

# 异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_async() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖: db: AsyncSession = Depends(get_db_async).

    行为约定:
    - 业务代码负责 commit, 自己控制事务边界.
    - 异常时兜底 rollback, 不让 pending transaction 泄漏.
    - 退出时显式 close, 把连接还回连接池.
    """
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception:
        try:
            await db.rollback()
            logger.warning("数据库会话发生异常, 已回滚")
        except Exception:
            logger.exception("数据库会话回滚失败")
        raise
    finally:
        try:
            await db.close()
        except Exception:
            logger.exception("数据库会话关闭失败")


async def check_db_connection() -> bool:
    """执行 SELECT 1 检查数据库连通性."""
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            alive = bool(result.scalar() == 1)
        logger.info("数据库连通性检查结果: %s", "OK" if alive else "FAIL")
        return alive
    except Exception:
        logger.exception("数据库连通性检查失败")
        return False


async def close_database() -> None:
    """关闭数据库引擎, 释放连接池资源."""
    try:
        await async_engine.dispose()
        logger.info("数据库引擎已释放")
    except Exception:
        logger.exception("数据库引擎释放失败")


if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        print("=" * 60)
        print("数据库连接层演示")
        print("=" * 60)
        print(f"驱动: {async_engine.url.drivername}")
        print(f"连通性: {await check_db_connection()}")
        await close_database()

    asyncio.run(_demo())
