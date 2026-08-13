"""AI 助手 HTTP 入口；LLM 异常不会影响风控主接口。"""

from fastapi import APIRouter

from app.agent.chat import chat as agent_chat
from app.agent.chat import clear_session
from app.schemas import AgentChatRequest, AgentChatResponse


router = APIRouter(prefix="/api/agent", tags=["AI风控助手"])


@router.post("/chat", response_model=AgentChatResponse)
async def chat(data: AgentChatRequest) -> AgentChatResponse:
    reply, session_id, available = await agent_chat(data.message, data.session_id)
    return AgentChatResponse(reply=reply, session_id=session_id, model_available=available)


@router.post("/clear")
async def clear(session_id: str) -> dict[str, str]:
    existed = await clear_session(session_id)
    return {"detail": "会话已清除" if existed else "会话不存在或已清除"}
