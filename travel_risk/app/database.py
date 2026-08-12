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


# 引擎注册表: rebuild_engine() 会新建引擎, 但脚本里 import 时绑定的旧引擎
# 可能仍在用, dispose 必须关掉所有已创建引擎 (否则退出时 aiomysql 报
# "Event loop is closed").
_ENGINES: list = []


def _create_engine(db_name: str | None = None):
    eng = create_async_engine(
        settings.get_database_url_async(db_name),
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )
    _ENGINES.append(eng)
    return eng


engine = _create_engine()

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
    engine = _create_engine(db_name)
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def dispose_engine():
    """释放全部已创建引擎的连接池 (一次性脚本退出前调用,
    避免 aiomysql 在解释器退出时报 "Event loop is closed")."""
    for eng in list(_ENGINES):
        try:
            await eng.dispose()
        except Exception as e:  # pragma: no cover - 清理阶段异常不阻塞
            logger.debug("引擎释放失败(忽略): %s", e)
    _ENGINES.clear()
