"""
银行风控系统 - 数据库连接管理
==========================
提供 SQLAlchemy 异步引擎和 Session 工厂.
默认连接 bank_risk 数据库.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import settings

# 异步引擎 (echo=False=不打印SQL, pool_size=10 默认连接池)
engine = create_async_engine(
    settings.get_database_url_async(),
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

# Session 工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_async():
    """FastAPI 依赖注入: 每次请求创建一个新的异步 Session, 请求结束自动关闭"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
