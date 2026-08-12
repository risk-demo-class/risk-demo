"""
AI 助手内置规则模式「第N项」解析回归测试.

背景 (2026-08-11): chat.html 欢迎语改成带序号 (1-6 项),
内置规则模式 _rule_reply 需要支持「第N项」说法.

跑法: pytest tests/test_agent_chat_numbered.py -v
"""
import pytest

from app.agent.chat import _rule_reply


@pytest.mark.asyncio
async def test_numbered_item_2_queries_cases():
    """第2项 → 案件查询, 返回 JSON 含 cases."""
    r = await _rule_reply("帮我查一下第2项")
    assert "query_cases" in r and "cases" in r


@pytest.mark.asyncio
async def test_numbered_item_5_queries_blacklist():
    """第5项 → 黑名单列表."""
    r = await _rule_reply("查第5项")
    assert "manage_blacklist" in r and "total" in r


@pytest.mark.asyncio
async def test_numbered_item_1_guides_params():
    """第1项 (风险检查) 缺参数 → 返回引导话术, 不报错."""
    r = await _rule_reply("第1项是什么")
    assert "风险检查" in r and "ORD003" in r


@pytest.mark.asyncio
async def test_numbered_item_4_guides_stats():
    """第4项 (统计) → 引导示例."""
    r = await _rule_reply("第4项是干嘛的")
    assert "统计" in r


@pytest.mark.asyncio
async def test_plain_digit_5_queries_blacklist():
    """纯数字 5 (欢迎语序号) → 黑名单列表."""
    r = await _rule_reply("5")
    assert "manage_blacklist" in r and "total" in r


@pytest.mark.asyncio
async def test_plain_digit_2_queries_cases():
    """纯数字 2 → 案件查询."""
    r = await _rule_reply("2")
    assert "query_cases" in r and "cases" in r


@pytest.mark.asyncio
async def test_plain_digit_1_guides_params():
    """纯数字 1 (风险检查, 缺参数) → 引导话术."""
    r = await _rule_reply("1")
    assert "风险检查" in r
