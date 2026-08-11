"""AI Agent 对话 API"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin
from app.agent.chat import chat, clear_session
from app.config import settings
from app.schemas import AgentChatRequest, AgentChatResponse


# 整个 Agent 路由要求登录: chat 会调 LLM + 工具 (含业务数据查询), 必须鉴权
agent_router = APIRouter(prefix="/api/agent", tags=["AI Agent"], dependencies=[Depends(require_admin)])


@agent_router.post("/chat", response_model=AgentChatResponse)
async def api_agent_chat(data: AgentChatRequest):
    try:
        # asyncio.wait_for 加超时, 防 LLM 网络挂死
        reply, session_id = await asyncio.wait_for(
            chat(data.message, data.session_id),
            timeout=settings.AI_AGENT_CHAT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"AI Agent 响应超时 (>{settings.AI_AGENT_CHAT_TIMEOUT_SEC}s), 请重试或简化问题",
        )
    return AgentChatResponse(reply=reply, session_id=session_id)


@agent_router.post("/clear")
async def api_clear_session(session_id: str):
    await clear_session(session_id)
    return {"detail": "已清除"}
