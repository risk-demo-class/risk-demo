"""AI Agent API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.chat import chat
from app.database import get_db_async
from app.schemas import AgentChatRequest, AgentChatResponse

router = APIRouter(prefix="/api/agent", tags=["Agent"])


@router.post("/chat", response_model=AgentChatResponse)
async def api_agent_chat(
    request: AgentChatRequest,
    db: AsyncSession = Depends(get_db_async),
) -> AgentChatResponse:
    """轻量 Agent 回复."""
    session_id = request.session_id or "default"
    reply = await chat(db, request.message)
    return AgentChatResponse(session_id=session_id, reply=reply)
