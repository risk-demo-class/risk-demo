"""
LLM 客户端: OpenAI 兼容 /chat/completions 协议
(阿里云百炼 / DeepSeek / 通义千问 等均可用)
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def llm_configured() -> bool:
    """是否已配置 LLM (API Key + Base URL 都有才启用)."""
    return bool((settings.LLM_API_KEY or "").strip() and (settings.LLM_BASE_URL or "").strip())


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 800,
) -> str:
    """调用 LLM 对话补全, 返回回复文本."""
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=settings.AI_AGENT_CHAT_TIMEOUT_SEC) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
