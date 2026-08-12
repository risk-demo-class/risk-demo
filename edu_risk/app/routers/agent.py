"""AI Agent 聊天接口"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.chat import get_agent, stream_chat
from app.database import get_db

router = APIRouter(prefix="/api/agent", tags=["AI 助手"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户问题")
    session_id: str = Field(default="default", description="会话 ID")
    user_id: str = Field(default="ops_admin", description="当前操作员")


@router.post("/chat")
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    """与 AI 风控助手对话(SSE 流式)。"""
    agent = get_agent()
    return StreamingResponse(
        stream_chat(agent, payload.session_id, payload.message, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
