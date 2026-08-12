import pytest

from app.agent.tools import TOOL_MANIFEST, execute_tool


def test_agent_has_eight_typed_tools() -> None:
    assert len(TOOL_MANIFEST) == 8
    names = {tool["name"] for tool in TOOL_MANIFEST}
    assert "risk_check" in names
    assert "query_graph_relations" in names
    assert "submit_review_request" in names


def test_only_request_tool_requires_approval() -> None:
    approval_tools = [tool for tool in TOOL_MANIFEST if tool["approval"]]
    assert len(approval_tools) == 1
    assert approval_tools[0]["name"] == "submit_review_request"
    assert approval_tools[0]["mode"] == "request"
    assert "approval_token" in approval_tools[0]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_request_tool_cannot_write_without_approval_token() -> None:
    result = await execute_tool(
        "submit_review_request",
        {"case_id": "CASE_ANY", "operator": "agent", "reason": "test"},
    )
    assert result["ok"] is False
    assert result["approval_required"] is True
