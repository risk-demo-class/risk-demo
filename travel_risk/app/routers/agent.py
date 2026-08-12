"""AI Agent API: 规则风险问诊 (未配置 LLM 时自动降级为规则式问答)"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.chat import handle_chat
from app.agent.llm import llm_configured
from app.config import settings
from app.database import get_db_async

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@agent_router.get("/health")
async def agent_health():
    return {
        "enabled": llm_configured(),
        "model": settings.LLM_MODEL_NAME if settings.LLM_API_KEY else "rule-fallback",
        "message": "LLM 已配置" if llm_configured() else "未配置 LLM, Agent 使用规则式降级问答",
    }


@agent_router.post("/chat")
async def agent_chat(body: ChatRequest, db: AsyncSession = Depends(get_db_async)):
    return await handle_chat(db, body.message, body.session_id)
