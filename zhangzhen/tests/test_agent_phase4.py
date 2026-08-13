"""8 个 Agent 工具、脱敏、写权限和会话锁测试。"""

import asyncio
import json

from app.agent import chat as chat_module
from app.agent.tools import (
    ALL_TOOL_NAMES,
    _manage_blacklist_impl,
    _query_banking_data_impl,
    build_langchain_tools,
)
from scripts.seed_demo_data import seed_demo_data


def test_agent_exposes_exactly_eight_typed_tools():
    tools = build_langchain_tools()
    assert len(tools) == 8
    assert tuple(tool.name for tool in tools) == ALL_TOOL_NAMES
    assert all(tool.args_schema is not None for tool in tools)


async def test_blacklist_write_is_rejected_in_backend(session_factory):
    async with session_factory() as db:
        result = await _manage_blacklist_impl(
            db=db, action="add", blacklist_type=None, value="U10001"
        )
    payload = json.loads(result)
    assert payload["restricted"] is True
    assert "人工确认" in payload["message"]


async def test_banking_data_is_masked_before_llm(session_factory):
    async with session_factory() as db:
        async with db.begin():
            await seed_demo_data(db)
        result = await _query_banking_data_impl(
            db=db, query_type="customer", user_id="U10001", limit=10
        )
    assert "id_card_hash" not in result
    assert "mobile_hash" not in result
    assert "name_hash" not in result
    assert json.loads(result)["user_id"] == "U10001"


async def test_same_agent_session_is_serialized(monkeypatch):
    chat_module.reset_agent_for_tests()
    monkeypatch.setattr(chat_module, "model_is_configured", lambda: True)
    active = 0
    maximum = 0

    async def fake_invoke(history, message):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.02)
        active -= 1
        return f"ok:{message}", [*history, message]

    monkeypatch.setattr(chat_module, "_invoke_agent", fake_invoke)
    first, second = await asyncio.gather(
        chat_module.chat("第一条", "same-session"),
        chat_module.chat("第二条", "same-session"),
    )
    assert maximum == 1
    assert first[1] == second[1] == "same-session"


async def test_agent_failure_degrades_without_raising(monkeypatch):
    chat_module.reset_agent_for_tests()
    monkeypatch.setattr(chat_module, "model_is_configured", lambda: True)

    async def fail(_history, _message):
        raise RuntimeError("simulated provider outage")

    monkeypatch.setattr(chat_module, "_invoke_agent", fail)
    reply, session_id, available = await chat_module.chat("你好", "failure-session")
    assert "核心风控服务不受影响" in reply
    assert session_id == "failure-session"
    assert available is False
