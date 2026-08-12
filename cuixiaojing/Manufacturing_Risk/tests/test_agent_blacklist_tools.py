"""
AI 助手黑名单工具回归测试.

背景 (2026-08-11): LLM 调 manage_blacklist 时可能多传 reason 参数,
_list 收到 blacklist_type/value/reason 全部参数会 TypeError.
修复: list 单独调用; check/remove 签名加 reason: str = "" 兜底.
本测试锁定该行为, 防止回归.

跑法: pytest tests/test_agent_blacklist_tools.py -v
"""
import pytest

from app.agent.tools import _manage_blacklist_impl, _safe_call


@pytest.mark.asyncio
async def test_blacklist_list_accepts_extra_args():
    """list action: LLM 传了 type/value/reason 也不报错, 返回 total."""
    r = await _safe_call(
        "list", _manage_blacklist_impl,
        action="list", blacklist_type="经销商ID", value="", reason="多余参数",
    )
    assert "total" in r and "items" in r


@pytest.mark.asyncio
async def test_blacklist_check_accepts_reason():
    """check action: 多传 reason 不报错, D003 在风控黑名单里 (gen_data 造数)."""
    r = await _safe_call(
        "check", _manage_blacklist_impl,
        action="check", blacklist_type="经销商ID", value="D003", reason="LLM 可能多传",
    )
    assert "在风控黑名单中" in r


@pytest.mark.asyncio
async def test_blacklist_add_remove_roundtrip():
    """add → check → remove 全链路, 测试后清理, 不留脏数据."""
    # add
    r1 = await _safe_call(
        "add", _manage_blacklist_impl,
        action="add", blacklist_type="维修工", value="T999", reason="pytest 临时",
    )
    assert "已添加到风控黑名单" in r1
    # check (多传 reason 模拟 LLM 行为)
    r2 = await _safe_call(
        "check", _manage_blacklist_impl,
        action="check", blacklist_type="维修工", value="T999", reason="pytest 临时",
    )
    assert "在风控黑名单中" in r2
    # remove
    r3 = await _safe_call(
        "remove", _manage_blacklist_impl,
        action="remove", blacklist_type="维修工", value="T999", reason="",
    )
    assert "已从风控黑名单移除" in r3
    # 确认已删
    r4 = await _safe_call(
        "check", _manage_blacklist_impl,
        action="check", blacklist_type="维修工", value="T999", reason="",
    )
    assert "不在风控黑名单中" in r4


@pytest.mark.asyncio
async def test_blacklist_unknown_action():
    """未知 action 返回提示, 不抛异常."""
    r = await _safe_call(
        "unknown", _manage_blacklist_impl,
        action="unknown", blacklist_type="经销商ID", value="", reason="",
    )
    assert "不支持的操作" in r
