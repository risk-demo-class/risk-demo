"""
数据库连接管理: 异步 SQLAlchemy 引擎 / 会话 / Base
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


engine = create_async_engine(
    settings.get_database_url_async(),
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_async():
    """FastAPI 依赖: 每个请求一个会话"""
    async with AsyncSessionLocal() as session:
        yield session


def rebuild_engine(db_name: str | None = None):
    """重建引擎 (测试库切换用)."""
    global engine, AsyncSessionLocal
    engine = create_async_engine(
        settings.get_database_url_async(db_name),
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
