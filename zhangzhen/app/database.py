"""SQLAlchemy 2.0 全异步数据库连接层。"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models import Base


def build_async_engine(database_url: str | None = None) -> AsyncEngine:
    """创建异步引擎；MySQL 使用连接回收，SQLite 测试保持简单。"""

    url = database_url or settings.get_database_url_async()
    options: dict[str, object] = {"echo": settings.DEBUG}
    if url.startswith("mysql+"):
        options.update(pool_pre_ping=True, pool_recycle=3600)
    return create_async_engine(url, **options)


async_engine = build_async_engine()
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_async() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 数据库依赖；业务 Service 决定何时提交事务。"""

    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ping_database(engine: AsyncEngine | None = None) -> bool:
    """执行一次最小查询，用于就绪检查和初始化脚本。"""

    target = engine or async_engine
    async with target.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def create_all_tables(engine: AsyncEngine | None = None) -> None:
    target = engine or async_engine
    async with target.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_all_tables(engine: AsyncEngine | None = None) -> None:
    target = engine or async_engine
    async with target.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

