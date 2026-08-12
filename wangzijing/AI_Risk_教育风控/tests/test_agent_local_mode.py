"""AI助手无密钥时的本地只读查询回归测试。"""

import json

import pytest

from app.agent import chat as chat_module


class _FakeTool:
    def __init__(self, payload):
        self.payload = payload

    async def ainvoke(self, _args):
        return json.dumps(self.payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_dashboard_quick_question_works_without_llm_key(monkeypatch):
    monkeypatch.setattr(chat_module.settings, "LLM_API_KEY", "")
    monkeypatch.setattr(chat_module, "query_dashboard_stats", _FakeTool({
        "today_assessments": 12,
        "today_high_risk": 3,
        "pass_rate": 75.0,
        "pending_cases": 2,
        "trend_7d": [{"count": 12, "high_risk_count": 3}],
        "top_rules": [{"rule_id": "EDU004", "hit_count": 2}],
    }))
    chat_module._sessions.clear()

    reply, session_id = await chat_module.chat("查看今天的风控统计数据")

    assert session_id.startswith("sess_")
    assert "今日风控态势" in reply
    assert "今日评估：12 条" in reply
    assert "EDU004" in reply


@pytest.mark.asyncio
async def test_unknown_local_question_explains_supported_queries(monkeypatch):
    monkeypatch.setattr(chat_module.settings, "LLM_API_KEY", "")

    reply, _ = await chat_module.chat("请自由创作一篇文章")

    assert "本地查询模式" in reply
    assert "LLM_API_KEY" in reply


@pytest.mark.asyncio
async def test_llm_error_is_sanitized(monkeypatch):
    monkeypatch.setattr(chat_module.settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(chat_module, "get_agent", lambda: (_ for _ in ()).throw(RuntimeError("secret detail")))

    reply, _ = await chat_module.chat("测试模型")

    assert "AI服务暂时不可用" in reply
    assert "secret detail" not in reply
