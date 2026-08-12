"""AI Agent 单测: 关键词路由 (mock DB)"""
import asyncio
from types import SimpleNamespace

from app.agent.chat import handle_chat


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def all(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _FakeResult(self._rows)


def test_chat_help_fallback():
    reply = asyncio.run(handle_chat(_FakeDB([]), "你好", "s1"))
    assert "旅游风控助手" in reply["reply"]


def test_chat_empty_message():
    reply = asyncio.run(handle_chat(_FakeDB([]), "", "s1"))
    assert "请描述你的问题" in reply["reply"]


def test_chat_search_rules_no_result():
    reply = asyncio.run(handle_chat(_FakeDB([]), "搜索不存在的规则xyz", "s1"))
    assert "未找到" in reply["reply"]


def test_chat_search_rules_with_result():
    rule = SimpleNamespace(
        rule_id="R001", rule_name="单笔高额旅游订单", rule_category="下单欺诈",
        risk_level="高", risk_score=70, action="人工审核", description="测试描述",
    )
    reply = asyncio.run(handle_chat(_FakeDB([rule]), "搜索退改规则", "s1"))
    assert "R001" in reply["reply"]


def test_chat_features():
    reply = asyncio.run(handle_chat(_FakeDB([]), "列出特征", "s1"))
    assert "28 维特征" in reply["reply"]


def test_chat_response_has_mode():
    reply = asyncio.run(handle_chat(_FakeDB([]), "你好", "s1"))
    assert "mode" in reply
    assert reply["mode"] in ("llm", "rule")


def test_llm_configured_false_without_key(monkeypatch):
    from app.agent import llm as llm_mod
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert llm_mod.llm_configured() is False


def test_llm_configured_true_with_key(monkeypatch):
    from app.agent import llm as llm_mod
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert llm_mod.llm_configured() is True
