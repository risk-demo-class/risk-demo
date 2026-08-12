"""AI Agent 层单测 (无 DB 依赖): 无 Key 降级 / 工具清单 / HTTP 端点。"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.agent import chat as chat_mod
from app.agent import tools
from app.main import app


def test_tool_registry_has_expected_tools():
    names = {t.name for t in tools.ALL_TOOLS}
    assert names == {
        "risk_check", "query_cases", "query_user_profile", "manage_blacklist",
        "query_dashboard_stats", "analyze_risk_trend", "analyze_rule_effectiveness",
        "query_business_data",
    }
    assert len(tools.ALL_TOOLS) == 8


def test_chat_returns_guidance_when_no_llm_key(monkeypatch):
    # 未配置 RISK_LLM_API_KEY 时应优雅返回引导, 不发起 LLM 调用
    assert chat_mod.settings.LLM_API_KEY == ""
    reply, session_id = asyncio.run(chat_mod.chat("你好"))
    assert "RISK_LLM_API_KEY" in reply
    assert session_id.startswith("sess_")


def test_chat_endpoint_and_clear():
    client = TestClient(app)
    resp = client.post("/api/agent/chat", json={"message": "你好", "session_id": "sess_test"})
    assert resp.status_code == 200
    body = resp.json()
    assert "RISK_LLM_API_KEY" in body["reply"]
    assert body["session_id"] == "sess_test"

    clear = client.post("/api/agent/clear", params={"session_id": "sess_test"})
    assert clear.status_code == 200


def test_chat_page_renders():
    client = TestClient(app)
    resp = client.get("/chat")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
