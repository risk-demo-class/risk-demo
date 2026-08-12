"""Agent chat, tool execution and session endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.chat import agent_service
from app.agent.tools import execute_tool


router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/capabilities")
async def capabilities() -> dict:
    return agent_service.capabilities()


@router.post("/chat")
async def chat(data: ChatRequest) -> dict:
    try:
        reply, session_id, tools = await agent_service.chat(data.message, data.session_id)
        return {"reply": reply, "session_id": session_id, "tools_used": tools}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent execution failed: {exc}") from exc


@router.post("/tools/{tool_name}")
async def call_tool(tool_name: str, data: ToolRequest) -> dict:
    return await execute_tool(tool_name, data.arguments)


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str) -> dict:
    return {"cleared": await agent_service.clear_session(session_id)}
