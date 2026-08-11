"""Agent 会话持久化测试 (2026-08-11 P1): MySQL 表 + TTL 清理 (真实库).

每测试建独立 engine/session (不碰全局 AsyncSessionLocal), 避免
pytest-asyncio 每测试一个事件循环导致全局连接池跨 loop 复用崩溃.
"""
from datetime import datetime, timedelta

import ulid
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import chat as chat_module
from app.config import settings
from app.models import AgentSession


class TestSessionStorageArchitecture:
    """会话存储架构 (2026-08-11 P1): 进程内 dict + 锁 → MySQL 表."""

    def test_in_memory_lock_and_dict_removed(self):
        """内存 _sessions/_sessions_lock 已移除 (改 MySQL 表, 多 worker 共享)."""
        assert not hasattr(chat_module, "_sessions_lock")
        assert not hasattr(chat_module, "_sessions")

    def test_db_helpers_exist(self):
        assert callable(chat_module._load_history)
        assert callable(chat_module._save_history)
        assert callable(chat_module._cleanup_expired_sessions)
        assert callable(chat_module.clear_session)


async def _new_session():
    """建独立 engine + session, 返回 (db, engine) 由调用方负责 dispose."""
    engine = create_async_engine(settings.get_database_url_async())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return session_factory(), engine


@pytest.mark.asyncio
async def test_session_save_load_roundtrip():
    """会话历史写入 MySQL 后能完整读回 (含 AI 回复)."""
    sid = f"sess_test_{ulid.new().str.lower()}"
    db, engine = await _new_session()
    try:
        await chat_module._save_history(
            db, sid, [HumanMessage(content="你好"), AIMessage(content="您好")]
        )
        history = await chat_module._load_history(db, sid)
        assert len(history) == 2
        assert history[0].content == "你好"
        assert history[1].content == "您好"
        assert isinstance(history[1], AIMessage)
    finally:
        await db.execute(delete(AgentSession).where(AgentSession.session_id == sid))
        await db.commit()
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_ttl_cleanup_removes_stale_sessions(monkeypatch):
    """超过 TTL 未活动的会话被清理."""
    monkeypatch.setattr(settings, "AGENT_SESSION_TTL_HOURS", 24)
    stale_sid = f"sess_stale_{ulid.new().str.lower()}"
    fresh_sid = f"sess_fresh_{ulid.new().str.lower()}"
    db, engine = await _new_session()

    try:
        # 先建两条会话
        await chat_module._save_history(db, stale_sid, [HumanMessage(content="旧")])
        await chat_module._save_history(db, fresh_sid, [HumanMessage(content="新")])
        # 把 stale 的 last_active 改成 48 小时前 (超 TTL)
        row = (await db.execute(
            select(AgentSession).where(AgentSession.session_id == stale_sid)
        )).scalar_one()
        row.last_active = datetime.now() - timedelta(hours=48)
        await db.commit()

        deleted = await chat_module._cleanup_expired_sessions(db)
        assert deleted >= 1
        # stale 已删, fresh 保留
        remain = (await db.execute(
            select(AgentSession.session_id).where(
                AgentSession.session_id.in_([stale_sid, fresh_sid])
            )
        )).scalars().all()
        assert stale_sid not in remain
        assert fresh_sid in remain
    finally:
        await db.execute(
            delete(AgentSession).where(AgentSession.session_id.in_([stale_sid, fresh_sid]))
        )
        await db.commit()
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_delete_removes_row():
    """删除指定会话后查不到."""
    sid = f"sess_clear_{ulid.new().str.lower()}"
    db, engine = await _new_session()
    try:
        await chat_module._save_history(db, sid, [HumanMessage(content="x")])
        result = await db.execute(
            delete(AgentSession).where(AgentSession.session_id == sid)
        )
        await db.commit()
        assert result.rowcount == 1
        remain = (await db.execute(
            select(AgentSession).where(AgentSession.session_id == sid)
        )).scalar_one_or_none()
        assert remain is None
    finally:
        await db.close()
        await engine.dispose()
