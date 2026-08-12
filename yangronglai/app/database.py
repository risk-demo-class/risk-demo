"""Lazy asynchronous MySQL engine/session lifecycle."""

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


class Base(DeclarativeBase):
    """Declarative base used by the business and risk ORM modules."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        database_url = settings.database_url()
        if database_url.drivername.startswith("sqlite") and database_url.database != ":memory:":
            from pathlib import Path

            Path(database_url.database).parent.mkdir(parents=True, exist_ok=True)
        engine_options: dict = {"pool_pre_ping": True}
        if database_url.drivername.startswith("mysql"):
            engine_options["pool_recycle"] = 1800
        _engine = create_async_engine(database_url, **engine_options)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


async def database_ping() -> bool:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
