"""
数据库层 — 全异步 SQLAlchemy 2.x
连接池 10+20,pool_recycle=3600s,显式 close 防 aiomysql 跨 event loop 异常。
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

async_engine = create_async_engine(
    settings.get_database_url_async(),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型统一继承,启动时 metadata 自动汇总全部表。"""


async def get_db():
    """FastAPI 依赖:每个请求一个 session,显式 close。"""
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()
