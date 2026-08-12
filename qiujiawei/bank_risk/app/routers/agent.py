"""AI Agent 对话 API"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bank_risk.app.agent.chat import run_agent, run_agent_stream


agent_router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


class AgentChatRequest(BaseModel):
    """Agent 对话请求体"""
    message: str


@agent_router.post("/chat")
async def api_agent_chat(data: AgentChatRequest):
    """AI Agent 对话 (同步返回完整回复)."""
    reply = await run_agent(data.message)
    return {"reply": reply}


@agent_router.post("/chat/stream")
async def api_agent_chat_stream(data: AgentChatRequest):
    """AI Agent 流式对话 (SSE)."""
    async def event_stream():
        async for chunk in run_agent_stream(data.message):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
